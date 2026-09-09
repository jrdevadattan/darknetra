import { createHash } from "node:crypto";

const API = "https://blockstream.info/api";
const EXPLORER = "https://blockstream.info";
const MAX_MONEY = 2_100_000_000_000_000n;
const fail = (code, message) => Object.assign(new Error(message), { code });
const badData = () =>
  fail(
    "SOURCE_INVALID_DATA",
    "The public chain source returned invalid or imprecise transaction data.",
  );
const hash = (bytes) => createHash("sha256").update(bytes).digest();
const base58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
const bech32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l";

// Validate mainnet address encodings; never infer a network from generic text.
export function bitcoinAddress(value) {
  if (typeof value !== "string" || value !== value.trim())
    throw fail(
      "VALIDATION",
      "Supply one Bitcoin mainnet address without surrounding text.",
    );
  if (/^[13][1-9A-HJ-NP-Za-km-z]{25,34}$/.test(value)) {
    let n = 0n;
    for (const char of value) n = n * 58n + BigInt(base58.indexOf(char));
    let hex = n.toString(16);
    if (hex.length % 2) hex = `0${hex}`;
    const bytes = Buffer.concat([
      Buffer.alloc(value.match(/^1*/)[0].length),
      Buffer.from(hex, "hex"),
    ]);
    if (
      bytes.length === 25 &&
      [0, 5].includes(bytes[0]) &&
      hash(hash(bytes.subarray(0, 21)))
        .subarray(0, 4)
        .equals(bytes.subarray(21))
    )
      return value;
  }
  if (
    /^(bc1|BC1)[a-zA-Z0-9]{11,71}$/.test(value) &&
    (value === value.toLowerCase() || value === value.toUpperCase())
  ) {
    const chars = [...value.toLowerCase().slice(3)].map((char) =>
      bech32.indexOf(char),
    );
    if (chars.every((char) => char >= 0)) {
      const expanded = [3, 3, 0, 2, 3]; // HRP expansion for "bc".
      let checksum = 1;
      for (const char of [...expanded, ...chars]) {
        const top = checksum >>> 25;
        checksum = ((checksum & 0x1ffffff) << 5) ^ char;
        [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3].forEach(
          (generator, index) => {
            if ((top >>> index) & 1) checksum ^= generator;
          },
        );
      }
      const version = chars[0];
      const program = chars.slice(1, -6);
      let accumulator = 0,
        bits = 0;
      const decoded = [];
      for (const char of program) {
        accumulator = ((accumulator << 5) | char) & 0xfff;
        bits += 5;
        if (bits >= 8) {
          bits -= 8;
          decoded.push((accumulator >>> bits) & 255);
        }
      }
      const paddingValid =
        bits < 5 && ((accumulator << (8 - bits)) & 255) === 0;
      if (
        version <= 16 &&
        paddingValid &&
        decoded.length >= 2 &&
        decoded.length <= 40 &&
        (version !== 0 || [20, 32].includes(decoded.length)) &&
        checksum >>> 0 === (version === 0 ? 1 : 0x2bc830a3)
      )
        return value.toLowerCase();
    }
  }
  throw fail(
    "VALIDATION",
    "This is not a valid Bitcoin mainnet address. Specify the actual network; unsupported networks are not queried.",
  );
}

function integer(value) {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0)
    throw badData();
  return value;
}

function sats(value, bounded = true) {
  const result = BigInt(integer(value));
  if (bounded && result > MAX_MONEY) throw badData();
  return result;
}

export function walletAmount(value) {
  if (typeof value !== "bigint") throw badData();
  const sign = value < 0n ? "-" : "";
  const magnitude = value < 0n ? -value : value;
  return {
    satoshis: value.toString(),
    btc: `${sign}${magnitude / 100_000_000n}.${(magnitude % 100_000_000n).toString().padStart(8, "0")}`,
  };
}

function scriptAddress(value) {
  if (value === undefined || value === null) return null; // E.g. an OP_RETURN output has no address.
  if (typeof value !== "string" || !/^[a-zA-Z0-9]{14,90}$/.test(value))
    throw badData();
  return value.startsWith("BC1") ? value.toLowerCase() : value;
}

function txHash(value) {
  if (typeof value !== "string" || !/^[a-f0-9]{64}$/.test(value))
    throw badData();
  return value;
}

function transaction(raw, address, tip, sourceUrl) {
  if (
    !raw ||
    !Array.isArray(raw.vin) ||
    !raw.vin.length ||
    !Array.isArray(raw.vout) ||
    !raw.vout.length ||
    raw.vin.length > 2000 ||
    raw.vout.length > 2000 ||
    typeof raw.status?.confirmed !== "boolean"
  )
    throw badData();
  const txid = txHash(raw.txid);
  const inputs = raw.vin.map((input, index) => {
    if (input.is_coinbase === true)
      return {
        index,
        txid: null,
        vout: null,
        address: null,
        amount: null,
        isCoinbase: true,
      };
    if (!input.prevout) throw badData();
    return {
      index,
      txid: txHash(input.txid),
      vout: integer(input.vout),
      address: scriptAddress(input.prevout.scriptpubkey_address),
      amount: walletAmount(sats(input.prevout.value)),
      isCoinbase: false,
    };
  });
  const outputs = raw.vout.map((output, index) => ({
    index,
    address: scriptAddress(output.scriptpubkey_address),
    amount: walletAmount(sats(output.value)),
  }));
  const spent = inputs.reduce(
    (total, input) =>
      total + (input.address === address ? BigInt(input.amount.satoshis) : 0n),
    0n,
  );
  const received = outputs.reduce(
    (total, output) =>
      total +
      (output.address === address ? BigInt(output.amount.satoshis) : 0n),
    0n,
  );
  if (
    !inputs.some((input) => input.address === address) &&
    !outputs.some((output) => output.address === address)
  )
    throw badData();
  const confirmed = raw.status.confirmed;
  const blockHeight = confirmed ? integer(raw.status.block_height) : null;
  const timestamp = confirmed ? integer(raw.status.block_time) : null;
  if (timestamp !== null && timestamp > 253402300799) throw badData();
  const outputTotal = outputs.reduce(
    (total, output) => total + BigInt(output.amount.satoshis),
    0n,
  );
  const inputTotal = inputs.reduce(
    (total, input) =>
      total + (input.amount ? BigInt(input.amount.satoshis) : 0n),
    0n,
  );
  const fee = sats(raw.fee);
  if (
    outputTotal > MAX_MONEY ||
    inputTotal > MAX_MONEY ||
    (!inputs.some((input) => input.isCoinbase) &&
      inputTotal - outputTotal !== fee)
  )
    throw badData();
  return {
    txid,
    url: `${EXPLORER}/tx/${txid}`,
    sourceUrl,
    status: {
      confirmed,
      blockHeight,
      blockTime:
        timestamp === null ? null : new Date(timestamp * 1000).toISOString(),
      confirmations: confirmed
        ? tip !== null && tip >= blockHeight
          ? tip - blockHeight + 1
          : null
        : 0,
    },
    direction:
      spent > 0n
        ? received > 0n
          ? "spent_and_received"
          : "spent"
        : "received",
    addressReceived: walletAmount(received),
    addressSpent: walletAmount(spent),
    addressNet: walletAmount(received - spent),
    fee: walletAmount(fee),
    inputs,
    outputs,
    interpretation:
      "Spent is the queried address's input value; received is its output value. Net includes its balance change, not a payment-to-counterparty amount. Inputs and outputs appearing together do not establish ownership or per-input funds provenance; fee is for the whole transaction.",
  };
}

function stats(raw, address) {
  if (!raw || scriptAddress(raw.address) !== address) throw badData();
  const parse = (data) => {
    if (!data) throw badData();
    const funded = sats(data.funded_txo_sum, false),
      spent = sats(data.spent_txo_sum, false);
    return {
      transactionCount: integer(data.tx_count),
      fundedOutputs: integer(data.funded_txo_count),
      spentOutputs: integer(data.spent_txo_count),
      received: walletAmount(funded),
      spent: walletAmount(spent),
      balanceChange: walletAmount(funded - spent),
    };
  };
  return {
    confirmed: parse(raw.chain_stats),
    mempool: parse(raw.mempool_stats),
  };
}

/** Exactly four public GET endpoints; supplied fetchSource retains the app's DNS/size/time checks. */
export async function walletReview(network, value, options = {}) {
  if (network !== "bitcoin")
    throw fail(
      "UNSUPPORTED_NETWORK",
      "Wallet review currently supports explicitly selected Bitcoin mainnet only. Other networks require a reviewed network-specific reader.",
    );
  const address = bitcoinAddress(value);
  const limit = options.limit === undefined ? 25 : Number(options.limit);
  if (!Number.isInteger(limit) || limit < 1 || limit > 25)
    throw fail("VALIDATION", "Choose a transaction limit from 1 to 25.");
  if (typeof options.fetchSource !== "function")
    throw fail(
      "CONFIGURATION",
      "Wallet review requires the bounded public source reader.",
    );
  const failures = [],
    sources = [];
  const paths = [
    `/address/${address}`,
    `/address/${address}/txs/chain`,
    `/address/${address}/txs/mempool`,
    "/blocks/tip/height",
  ];
  const responses = await Promise.all(
    paths.map(async (path) => {
      const url = `${API}${path}`;
      try {
        const result = await options.fetchSource(url);
        if (
          result.url !== url ||
          typeof result.body !== "string" ||
          Buffer.byteLength(result.body) > 1_000_000 ||
          !Number.isFinite(Date.parse(result.fetchedAt))
        )
          throw badData();
        const data = JSON.parse(result.body);
        sources.push({
          url,
          fetchedAt: result.fetchedAt,
          contentSha256: createHash("sha256").update(result.body).digest("hex"),
        });
        return { data, url, fetchedAt: result.fetchedAt };
      } catch (error) {
        const code = [
          "SIZE_LIMIT",
          "UPSTREAM_UNAVAILABLE",
          "POLICY_DENIED",
          "SOURCE_INVALID_DATA",
        ].includes(error.code)
          ? error.code
          : "UPSTREAM_UNAVAILABLE";
        failures.push({
          url,
          code,
          message:
            code === "SOURCE_INVALID_DATA"
              ? "The source response could not be validated."
              : "The public chain record could not be read. This is not evidence of an empty history.",
        });
        return null;
      }
    }),
  );
  let addressStats = null,
    tip = null;
  for (const [index, parse] of [
    [
      0,
      (data) => {
        addressStats = stats(data, address);
      },
    ],
    [
      3,
      (data) => {
        tip = integer(data);
      },
    ],
  ]) {
    if (responses[index]) {
      try {
        parse(responses[index].data);
      } catch {
        failures.push({
          url: responses[index].url,
          code: "SOURCE_INVALID_DATA",
          message: "The source summary could not be validated.",
        });
      }
    }
  }
  const candidates = [],
    history = [];
  for (const [index, max, confirmed] of [
    [2, 50, false],
    [1, 25, true],
  ]) {
    const response = responses[index];
    if (!response) {
      history.push({ confirmed, available: false, fetched: 0 });
      continue;
    }
    if (!Array.isArray(response.data) || response.data.length > max) {
      failures.push({
        url: response.url,
        code: "SOURCE_INVALID_DATA",
        message: "The transaction list could not be validated.",
      });
      history.push({ confirmed, available: false, fetched: 0 });
      continue;
    }
    history.push({ confirmed, available: true, fetched: response.data.length });
    for (const item of response.data) {
      try {
        if (item?.status?.confirmed !== confirmed) throw badData();
        candidates.push(transaction(item, address, tip, response.url));
      } catch {
        failures.push({
          url: response.url,
          code: "SOURCE_INVALID_DATA",
          ...(typeof item?.txid === "string" && /^[a-f0-9]{64}$/.test(item.txid)
            ? { txid: item.txid }
            : {}),
          message:
            "A transaction was omitted because its amounts or fields could not be validated.",
        });
      }
    }
  }
  if (!history.some((item) => item.available))
    throw fail(
      "UPSTREAM_UNAVAILABLE",
      "Neither confirmed nor unconfirmed transaction history could be read. No finding about wallet activity can be made.",
    );
  const seen = new Set();
  const unique = candidates.filter(
    (item) => !seen.has(item.txid) && seen.add(item.txid),
  );
  const transactions = unique.slice(0, limit);
  const confirmedHistory = history.find((item) => item.confirmed);
  const mempoolHistory = history.find((item) => !item.confirmed);
  const fetchedAt = sources.reduce(
    (latest, source) => (source.fetchedAt > latest ? source.fetchedAt : latest),
    "",
  );
  const coverage = {
    state: failures.length ? "partial" : "bounded",
    historyComplete: false,
    confirmedPageLimit: 25,
    mempoolLimit: 50,
    confirmedHistory,
    mempoolHistory,
    returnedTransactions: transactions.length,
    validTransactionsFetched: unique.length,
    omittedByDisplayLimit: Math.max(0, unique.length - limit),
    providerConfirmedCount: addressStats?.confirmed.transactionCount ?? null,
    providerMempoolCount: addressStats?.mempool.transactionCount ?? null,
    confirmedMoreAvailable: confirmedHistory.available
      ? addressStats
        ? addressStats.confirmed.transactionCount > confirmedHistory.fetched
        : confirmedHistory.fetched === 25
          ? true
          : null
      : null,
    tipHeight: tip,
    scope:
      "Only the supplied address's first confirmed page and bounded unconfirmed records were requested. No counterparty histories, spent-output tracing, older pages, other chains or off-chain records were retrieved. Mempool records are shown first. Provider snapshots may change between requests.",
  };
  const ml = {
    state: "not_ready",
    model: "GraphSAGE",
    featureSpace: "elliptic-raw-102-v1",
    reason:
      "Raw address transactions are not the model's input. There is no validated raw-chain feature extractor in this app; no inference was run.",
    missingRequirements: [
      "102 finite, unscaled training-compatible features per transaction in the exact ml-schema order",
      "A directed edge_index with the model's required graph context and a target node_index",
      "Feature provenance and prediction-time cutoff compatible with the training pipeline",
    ],
    nextStep:
      "Request the compatible transaction graph from the model/data team, then use ml-predict on that supplied file. Keep independent source analysis alongside any model result; never fill unknown features with zeros.",
  };
  return {
    analysis: "wallet_review",
    network,
    address,
    title: `Bitcoin public transaction review: ${address}`,
    url:
      sources.find((source) => source.url === `${API}${paths[0]}`)?.url ||
      sources.find((source) => source.url.includes("/txs/"))?.url,
    explorerUrl: `${EXPLORER}/address/${address}`,
    fetchedAt,
    text: `Reviewed ${transactions.length} validated Bitcoin transactions for the supplied address, from one confirmed page and bounded mempool records. ${failures.length ? `${failures.length} source or validation failures leave gaps. ` : ""}This is a bounded public-record review, not a complete wallet history or a finding of wrongdoing. Exact amounts and input/output references are below. Exchange identity and KYC are not supplied by this source. ML was not run: the required 102-feature transaction graph is unavailable.`,
    addressStats,
    transactions,
    coverage,
    failures,
    sources,
    ml,
    exchangeAttribution: {
      state: "unavailable",
      labels: [],
      reason:
        "This public Esplora API does not supply exchange ownership, customer identity or KYC records. An output address or shared transaction alone is not exchange attribution.",
    },
    nextSteps: [
      "If an independent, authorized attribution source reports an exchange-controlled address, retain its provider, source URL, retrieval time and exact claim; treat it as a lead for review.",
      "For an attributed exchange lead, an authorized investigator can ask the exchange's official legal/compliance channel which preservation or records process applies, with transaction ID, network, output index, address, amount and UTC time. No KYC data has been obtained; connecting a wallet does not reveal it.",
    ],
  };
}
