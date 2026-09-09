import { createHash } from "node:crypto";
import { expect, test, vi } from "vitest";
import { bitcoinAddress, walletAmount, walletReview } from "./wallet.mjs";

// SYNTHETIC addresses and transactions generated for deterministic tests; no live lookup.
const hash = (bytes) => createHash("sha256").update(bytes).digest();
function syntheticAddress(label) {
  const payload = Buffer.concat([
    Buffer.from([0]),
    hash(`SYNTHETIC-${label}`).subarray(0, 20),
  ]);
  const bytes = Buffer.concat([payload, hash(hash(payload)).subarray(0, 4)]);
  let n = BigInt(`0x${bytes.toString("hex")}`),
    encoded = "";
  const alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
  while (n) {
    encoded = alphabet[Number(n % 58n)] + encoded;
    n /= 58n;
  }
  return "1" + encoded;
}
const address = syntheticAddress("queried");
const other = syntheticAddress("other");
const timestamp = "2026-09-09T08:00:00.000Z";
const id = (n) => n.toString(16).padStart(64, "0");
const input = (wallet, value, n = 10) => ({
  txid: id(n),
  vout: 0,
  is_coinbase: false,
  prevout: { scriptpubkey_address: wallet, value },
});
const output = (wallet, value) => ({ scriptpubkey_address: wallet, value });
const tx = (n = 1) => ({
  txid: id(n),
  fee: 123,
  vin: [input(address, 10000123)],
  vout: [output(other, 9000000), output(address, 1000000)],
  status: { confirmed: true, block_height: 100, block_time: 1700000000 },
});
const emptyStats = {
  tx_count: 0,
  funded_txo_count: 0,
  spent_txo_count: 0,
  funded_txo_sum: 0,
  spent_txo_sum: 0,
};
const info = {
  address,
  chain_stats: {
    ...emptyStats,
    tx_count: 1,
    funded_txo_sum: 10000123,
    spent_txo_sum: 10000123,
  },
  mempool_stats: { ...emptyStats },
};
function source(patches = {}) {
  return vi.fn(async (url) => {
    const suffix = url.replace("https://blockstream.info/api", "");
    const value =
      patches[suffix] ??
      (suffix.endsWith("/txs/chain")
        ? [tx()]
        : suffix.endsWith("/txs/mempool")
          ? []
          : suffix.endsWith("/height")
            ? 102
            : info);
    if (value instanceof Error) throw value;
    return {
      url,
      body: JSON.stringify(value),
      fetchedAt: timestamp,
      mime: "application/json",
    };
  });
}

test("SYNTHETIC review uses exactly four fixed public endpoints and retains exact amounts and provenance", async () => {
  const fetchSource = source();
  const result = await walletReview("bitcoin", address, { fetchSource });
  expect(fetchSource).toHaveBeenCalledTimes(4);
  expect(
    fetchSource.mock.calls.every(([url]) =>
      url.startsWith("https://blockstream.info/api/"),
    ),
  ).toBe(true);
  expect(result.transactions[0]).toMatchObject({
    txid: id(1),
    sourceUrl: `https://blockstream.info/api/address/${address}/txs/chain`,
    status: {
      confirmed: true,
      blockHeight: 100,
      blockTime: "2023-11-14T22:13:20.000Z",
      confirmations: 3,
    },
    direction: "spent_and_received",
    addressSpent: { satoshis: "10000123", btc: "0.10000123" },
    addressReceived: { satoshis: "1000000", btc: "0.01000000" },
    addressNet: { satoshis: "-9000123", btc: "-0.09000123" },
    fee: { satoshis: "123", btc: "0.00000123" },
    inputs: [
      { txid: id(10), vout: 0, address, amount: { satoshis: "10000123" } },
    ],
    outputs: [
      { index: 0, address: other, amount: { satoshis: "9000000" } },
      { index: 1, address },
    ],
  });
  expect(result.transactions[0].interpretation).toContain(
    "do not establish ownership or per-input funds provenance",
  );
  expect(result.sources).toHaveLength(4);
  expect(
    result.sources.every(
      (entry) =>
        entry.fetchedAt === timestamp &&
        /^[a-f0-9]{64}$/.test(entry.contentSha256),
    ),
  ).toBe(true);
  expect(result.sources.map((entry) => entry.url)).not.toContain(
    result.transactions[0].url,
  );
  expect(result.coverage).toMatchObject({
    state: "bounded",
    historyComplete: false,
    returnedTransactions: 1,
    providerConfirmedCount: 1,
    confirmedMoreAvailable: false,
  });
  expect(result.ml).toMatchObject({
    state: "not_ready",
    featureSpace: "elliptic-raw-102-v1",
  });
  expect(result.ml).not.toHaveProperty("features");
  expect(result.exchangeAttribution).toMatchObject({
    state: "unavailable",
    labels: [],
  });
  expect(result.nextSteps.join(" ")).toContain(
    "connecting a wallet does not reveal it",
  );
});

test("SYNTHETIC unsupported networks, invalid checksums, injected URLs and bad limits fail before network I/O", async () => {
  const fetchSource = vi.fn();
  await expect(
    walletReview("ethereum", `0x${"a".repeat(40)}`, { fetchSource }),
  ).rejects.toMatchObject({ code: "UNSUPPORTED_NETWORK" });
  for (const value of [
    "https://example.com/",
    `${address}/txs`,
    ` ${address}`,
    address.slice(0, -1) + (address.endsWith("1") ? "2" : "1"),
    "bc1invalidaddress",
    `bc1${"a".repeat(80)}`,
  ])
    await expect(
      walletReview("bitcoin", value, { fetchSource }),
    ).rejects.toMatchObject({ code: "VALIDATION" });
  for (const limit of [0, 26, 1.5, "everything"])
    await expect(
      walletReview("bitcoin", address, { fetchSource, limit }),
    ).rejects.toMatchObject({ code: "VALIDATION" });
  expect(fetchSource).not.toHaveBeenCalled();
  expect(bitcoinAddress(address)).toBe(address);
});

test("SYNTHETIC validation agrees with public BIP-350 address test vectors without querying them", () => {
  // Specification fixtures: https://github.com/bitcoin/bips/blob/master/bip-0350.mediawiki
  for (const value of [
    "BC1QW508D6QEJXTDG4Y5R3ZARVARY0C5XW7KV8F3T4",
    "bc1pw508d6qejxtdg4y5r3zarvary0c5xw7kw508d6qejxtdg4y5r3zarvary0c5xw7kt5nd6y",
    "BC1SW50QGDZ25J",
    "bc1zw508d6qejxtdg4y5r3zarvaryvaxxpcs",
    "bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqzk5jj0",
  ])
    expect(bitcoinAddress(value)).toBe(value.toLowerCase());
  for (const value of [
    "bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqh2y7hd",
    "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kemeawh",
    "bc1pw5dgrnzv",
    "BC130XLXVLHEMJA6C4DQV22UAPCTQUPFHLXM9H8Z3K2E72Q4K9HCZ7VQ7ZWS8R",
    "BC1QR508D6QEJXTDG4Y5R3ZARVARYV98GJ9P",
    "bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7v07qwwzcrf",
    "tb1qrp33g0q5c5txsp9arysrx4k6zdkfs4nce4xj0gdcccefvpysxf3q0sl5k7",
  ])
    expect(() => bitcoinAddress(value)).toThrow();
});

test("SYNTHETIC display limits and provider counts disclose omitted history", async () => {
  const fetchSource = source({
    [`/address/${address}`]: {
      ...info,
      chain_stats: { ...info.chain_stats, tx_count: 300 },
    },
    [`/address/${address}/txs/chain`]: Array.from({ length: 25 }, (_, i) =>
      tx(i + 1),
    ),
    [`/address/${address}/txs/mempool`]: [
      { ...tx(99), status: { confirmed: false } },
    ],
  });
  const result = await walletReview("bitcoin", address, {
    fetchSource,
    limit: 2,
  });
  expect(result.transactions.map((entry) => entry.txid)).toEqual([
    id(99),
    id(1),
  ]);
  expect(result.transactions[0].status).toMatchObject({
    confirmed: false,
    blockTime: null,
    confirmations: 0,
  });
  expect(result.coverage).toMatchObject({
    historyComplete: false,
    confirmedMoreAvailable: true,
    validTransactionsFetched: 26,
    omittedByDisplayLimit: 24,
  });
});

test("SYNTHETIC missing history is disclosed and never rendered as no matches", async () => {
  const unavailable = Object.assign(
    new Error("SYNTHETIC upstream unavailable"),
    { code: "UPSTREAM_UNAVAILABLE" },
  );
  const fetchSource = source({
    [`/address/${address}/txs/chain`]: unavailable,
    "/blocks/tip/height": unavailable,
  });
  const result = await walletReview("bitcoin", address, { fetchSource });
  expect(result.coverage).toMatchObject({
    state: "partial",
    confirmedHistory: { available: false },
    tipHeight: null,
  });
  expect(result.text).toContain("failures leave gaps");
  expect(result.failures).toHaveLength(2);
  expect(result.sources).toHaveLength(2);
  await expect(
    walletReview("bitcoin", address, {
      fetchSource: source({
        [`/address/${address}/txs/chain`]: unavailable,
        [`/address/${address}/txs/mempool`]: unavailable,
      }),
    }),
  ).rejects.toMatchObject({ code: "UPSTREAM_UNAVAILABLE" });
});

test("SYNTHETIC unavailable chain tip does not turn confirmed records into zero confirmations", async () => {
  const result = await walletReview("bitcoin", address, {
    fetchSource: source({
      "/blocks/tip/height": new Error("SYNTHETIC unavailable"),
    }),
  });
  expect(result.transactions[0].status).toMatchObject({
    confirmed: true,
    confirmations: null,
  });
  expect(result.coverage.state).toBe("partial");
});

test("SYNTHETIC imprecise, inconsistent and unrelated transactions are excluded rather than interpreted", async () => {
  const unsafe = {
    ...tx(1),
    vout: [output(address, Number.MAX_SAFE_INTEGER + 1)],
  };
  const inconsistent = { ...tx(2), fee: 0.5 };
  const unbalanced = { ...tx(3), fee: 0 };
  const unrelated = {
    ...tx(4),
    vin: [input(other, 10000123)],
    vout: [output(other, 10000000)],
  };
  const missingPrevout = {
    ...tx(5),
    vin: [{ ...input(address, 10000123), prevout: null }],
  };
  const result = await walletReview("bitcoin", address, {
    fetchSource: source({
      [`/address/${address}/txs/chain`]: [
        unsafe,
        inconsistent,
        unbalanced,
        unrelated,
        missingPrevout,
        tx(6),
      ],
    }),
  });
  expect(result.transactions.map((entry) => entry.txid)).toEqual([id(6)]);
  expect(result.failures).toHaveLength(5);
  expect(
    result.failures.every((entry) => entry.code === "SOURCE_INVALID_DATA"),
  ).toBe(true);
  expect(result.coverage.state).toBe("partial");
});

test("SYNTHETIC mixed inputs retain all outputs without attributing a queried input to any recipient", async () => {
  const mixed = {
    ...tx(),
    vin: [input(address, 5000000), input(other, 5000123)],
    vout: [output(other, 10000000)],
  };
  const result = await walletReview("bitcoin", address, {
    fetchSource: source({ [`/address/${address}/txs/chain`]: [mixed] }),
  });
  expect(result.transactions[0]).toMatchObject({
    direction: "spent",
    addressSpent: { satoshis: "5000000" },
    addressNet: { satoshis: "-5000000" },
  });
  expect(result.transactions[0].outputs[0].amount.satoshis).toBe("10000000");
  expect(result.transactions[0]).not.toHaveProperty("sentTo");
  expect(walletAmount(1n)).toEqual({ satoshis: "1", btc: "0.00000001" });
  expect(walletAmount(-1n)).toEqual({ satoshis: "-1", btc: "-0.00000001" });
});

test("SYNTHETIC response overclaim and redirect output are rejected", async () => {
  const redirected = vi.fn(async (url) => ({
    url: url.replace("blockstream.info", "example.com"),
    body: "[]",
    fetchedAt: timestamp,
  }));
  await expect(
    walletReview("bitcoin", address, { fetchSource: redirected }),
  ).rejects.toMatchObject({ code: "UPSTREAM_UNAVAILABLE" });
  const result = await walletReview("bitcoin", address, {
    fetchSource: source({
      [`/address/${address}/txs/chain`]: Array.from({ length: 26 }, (_, i) =>
        tx(i),
      ),
    }),
  });
  expect(result.coverage).toMatchObject({
    state: "partial",
    confirmedHistory: { available: false },
  });
});
