"""Generate SYNTHETIC case fixtures. Private keys never leave process memory."""

import argparse
import hashlib
import html
import json
import random
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import base58
import pgpy
from bech32 import bech32_encode, convertbits
from fpdf import FPDF
from pgpy.constants import (
    CompressionAlgorithm,
    HashAlgorithm,
    KeyFlags,
    PubKeyAlgorithm,
    SymmetricKeyAlgorithm,
)
from PIL import Image, ImageDraw


def generate(out: Path, seed=20260906):
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    source_families = {}

    def write(name, content, source_family="SYNTHETIC_REFERENCE"):
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(
            content if isinstance(content, bytes) else content.encode("utf-8")
        )
        source_families[name] = source_family

    keys = {}
    for alias in ("A", "B"):
        path = out / f"keys/SYNTHETIC_ALIAS_{alias}.asc"
        if path.exists():
            key, _ = pgpy.PGPKey.from_blob(path.read_bytes())
            if not key.is_public:
                raise ValueError("Expected public-only SYNTHETIC key")
        else:
            private = pgpy.PGPKey.new(PubKeyAlgorithm.RSAEncryptOrSign, 2048)
            uid = pgpy.PGPUID.new(
                f"SYNTHETIC_ALIAS_{alias}",
                comment="SYNTHETIC TEST ONLY",
                email=f"synthetic-{alias.lower()}@example.invalid",
            )
            private.add_uid(
                uid,
                usage={KeyFlags.Sign, KeyFlags.EncryptCommunications},
                hashes=[HashAlgorithm.SHA256],
                ciphers=[SymmetricKeyAlgorithm.AES256],
                compression=[CompressionAlgorithm.ZLIB],
            )
            key = private.pubkey
            write(f"keys/SYNTHETIC_ALIAS_{alias}.asc", str(key))
            del private
        keys[alias] = key
        source_families[f"keys/SYNTHETIC_ALIAS_{alias}.asc"] = (
            f"SYNTHETIC_LISTING_{alias}"
        )
    wallet = bech32_encode("tb", [0] + convertbits(list(bytes(range(20))), 8, 5))
    escrow = base58.b58encode_check(bytes([111]) + bytes(reversed(range(20)))).decode()
    messages = []
    for i in range(300):
        day = i // 30 + 1
        sender = f"SYNTHETIC_SENDER_{i % 3}"
        text = f"SYNTHETIC exercise sample {i}: {rng.choice(['chitta', 'ਚਿੱਟਾ', 'चिट्टा', 'maal'])} {rng.choice([2, 5, 10])} gm INR {rng.choice([1500, 2500, 3000])}. Zirakpur classification example."
        if day >= 5:
            text += " safed line"
        if i % 3 == 0:
            text += " purani cheez"
        if i == 87:
            sender = "SYNTHETIC_ALIAS_A_CHAT"
            text += f" SYNTHETIC testnet wallet {wallet}"
        if i == 119:
            sender, text = "SYNTHETIC_ALIAS_A_CHAT", text + " wickr:synthetic_a_test"
        if i == 142:
            sender, text = "SYNTHETIC_ALIAS_A_CHAT", text + "\n" + str(keys["A"])
        messages.append(
            {
                "id": i + 1,
                "type": "message",
                "date": f"2026-09-{day:02d}T10:{i % 30:02d}:00",
                "from": sender,
                "text": text,
            }
        )
    telegram = json.dumps(
        {"name": "SYNTHETIC", "messages": messages}, ensure_ascii=False
    )
    write("telegram/result.json", telegram, "SYNTHETIC_CHAT_A")
    for alias in ("A", "B", "C"):
        key = str(keys[alias]) if alias in keys else "SYNTHETIC no public key"
        contact = (
            "wickr:synthetic_a_test"
            if alias == "A"
            else f"@synthetic_alias_{alias.lower()}"
        )
        body = f"SYNTHETIC training listing SYNTHETIC_ALIAS_{alias}\nVendor alias: SYNTHETIC_ALIAS_{alias}\nPublished at: 2026-09-01T10:00:00+00:00\n{contact}\nSYNTHETIC shared_service escrow testnet {escrow}\n{key}\nSYNTHETIC classification sample: safed line maal 2 gm INR 2500"
        if alias == "A":
            body += f"\nSYNTHETIC vendor-controlled testnet wallet {wallet}\nSYNTHETIC claimed location: Zirakpur"
        write(
            f"listings/SYNTHETIC_ALIAS_{alias}.html",
            "<!doctype html><html><body><h1>SYNTHETIC</h1><pre>"
            + html.escape(body)
            + "</pre></body></html>",
            f"SYNTHETIC_LISTING_{alias}",
        )
    shared_description = (
        "SYNTHETIC training profile. Amber lantern illustrations sit beside a blue paper notebook. "
        "The inventory description uses measured sentences and the same unusual phrase, quiet copper compass. "
        "Each illustration carries a visible test label and a neutral exercise number. "
        "The notebooks describe shapes, colours, and specimen labels for an evidence review exercise. "
        "These are authored synthetic text samples, and their shared phrasing is deliberately planted for testing. "
        "No real account, transaction, identity, sale, or procurement instruction is represented."
    )
    for alias, family in [
        ("SYNTHETIC_ALIAS_A", "SYNTHETIC_LISTING_A"),
        ("SYNTHETIC_ALIAS_A_CHAT", "SYNTHETIC_CHAT_A"),
    ]:
        body = f"SYNTHETIC supplementary authored profile\nVendor alias: {alias}\nPublished at: 2026-09-10T10:00:00+00:00\n{shared_description}\nSYNTHETIC claimed location: Zirakpur\nwickr:synthetic_a_test\nSYNTHETIC vendor-controlled testnet wallet {wallet}\n{keys['A']}"
        write(
            f"listings/{alias}_profile.html",
            "<!doctype html><html><body><pre>"
            + html.escape(body)
            + "</pre></body></html>",
            family,
        )
    write(
        "whatsapp/chat.txt",
        "\n".join(
            f"{i // 5 + 1}/9/2026, 10:{i % 5:02d} - SYNTHETIC_ALIAS_C: SYNTHETIC sample maal 2 tola INR 2500"
            for i in range(50)
        ),
        "SYNTHETIC_CHAT_B",
    )
    for name, color in [("product_a", "#c4d7bc"), ("unrelated", "#412faa")]:
        img = Image.new("RGB", (400, 300), color)
        draw = ImageDraw.Draw(img)
        draw.rectangle((100, 60, 300, 260), outline="black", width=8)
        draw.text((110, 140), "SYNTHETIC TEST", fill="black")
        target = out / f"images/{name}.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        img.save(target)
        source_families[f"images/{name}.jpg"] = "SYNTHETIC_IMAGE_LIBRARY"
        if name == "product_a":
            img.save(out / "images/product_a_copy.jpg", quality=40)
            source_families["images/product_a_copy.jpg"] = "SYNTHETIC_IMAGE_LIBRARY"
    pdf = FPDF()
    pdf.set_creation_date(datetime(2026, 9, 6, tzinfo=UTC))
    pdf.add_page()
    pdf.set_font("Helvetica", size=14)
    pdf.multi_cell(
        0,
        9,
        "SYNTHETIC seizure memo. Training exercise only.\nPolice seized heroin. No offer, sale or price is recorded. No real person is identified.",
    )
    write("docs/seizure_memo.pdf", bytes(pdf.output()))
    header = "source_class,node_index,timestep,label," + ",".join(
        f"f_{i}" for i in range(102)
    )
    write(
        "ledger/nodes.csv",
        header
        + "\n"
        + "\n".join(
            f"SYNTHETIC,{i},1,{1 if i < 2 else 2},"
            + ",".join(str(round(rng.random(), 6)) for _ in range(102))
            for i in range(8)
        ),
    )
    write(
        "ledger/edges.csv",
        "source_class,src,dst\n"
        + "\n".join(f"SYNTHETIC,{i},{i + 1}" for i in range(7)),
    )
    write(
        "ledger/address_map.csv",
        f"source_class,address,chain,node_index,tag\nSYNTHETIC,{wallet},BTC,0,vendor_controlled\nSYNTHETIC,{escrow},BTC,2,shared_service\n",
    )
    files = sorted(
        p
        for p in out.rglob("*")
        if p.is_file() and p.relative_to(out).as_posix() in source_families
    )
    manifest = {
        "source_class": "SYNTHETIC",
        "seed": seed,
        "ledger_caveat": "Random synthetic features; no trained-dataset provenance or meaningful GNN assessment",
        "files": [
            {
                "filename": p.relative_to(out).as_posix(),
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "source_class": "SYNTHETIC",
                "source_family": source_families[p.relative_to(out).as_posix()],
            }
            for p in files
        ],
    }
    write("manifest.json", json.dumps(manifest, indent=2))
    truth = {
        "source_class": "SYNTHETIC",
        "aliases": {
            "same_operator": [["SYNTHETIC_ALIAS_A", "SYNTHETIC_ALIAS_A_CHAT"]],
            "decoy_pairs": [["SYNTHETIC_ALIAS_A", "SYNTHETIC_ALIAS_B"]],
            "signals": ["pgp_fingerprint", "contact"],
        },
        "pgp": {k: str(v.fingerprint) for k, v in keys.items()},
        "wallets": {"W1": wallet, "W_escrow": escrow},
        "trend": {
            "term": "safed line",
            "first_day": 5,
            "senders": 3,
            "control_term": "purani cheez",
        },
        "planted_messages": {"pgp_paste": 143, "wallet": 88, "contact": 120},
        "files": [p.relative_to(out).as_posix() for p in files],
    }
    write("ground_truth.json", json.dumps(truth, indent=2))
    with zipfile.ZipFile(
        out / "bundle.zip", "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        for path in files:
            info = zipfile.ZipInfo(
                path.relative_to(out).as_posix(), date_time=(2026, 9, 6, 0, 0, 0)
            )
            archive.writestr(info, path.read_bytes())
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260906)
    parser.add_argument(
        "--out", type=Path, default=Path("data/synthetic/out/SYN-CHD-001")
    )
    args = parser.parse_args()
    manifest = generate(args.out, args.seed)
    print(f"Generated {len(manifest['files'])} SYNTHETIC items")
