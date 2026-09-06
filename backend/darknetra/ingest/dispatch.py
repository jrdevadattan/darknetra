"""Pure parsers. No external resources or active content are evaluated."""

import csv
import io
import json
import re
import warnings
from datetime import datetime, timedelta, timezone

import imagehash
import nh3
from PIL import Image, ImageOps
from pypdf import PdfReader
from selectolax.parser import HTMLParser

from darknetra.ingest.sniff import decode


def text_doc(text, contexts=()):
    return {
        "text": text,
        "line_offsets": [0] + [m.end() for m in re.finditer("\n", text)],
        "page_map": None,
        "contexts": list(contexts),
    }


def parse(data: bytes, kind: str, filename: str):
    derivatives, notices = [], []
    contexts = []
    text = None
    if kind == "HTML":
        tree = HTMLParser(decode(data))
        for node in tree.css("script,style,noscript,iframe,object,embed,form,input,link,meta,base"):
            node.decompose()
        for node in tree.css("a"):
            node.attrs["href"] = "#"
        text = tree.text(separator="\n", strip=True)
        publishers = list(re.finditer(r"(?im)^Vendor alias:\s*([^\n\r]{1,100})$", text))
        if len(publishers) == 1:
            publisher = publishers[0]
            contexts.append(
                {
                    "value": publisher[1],
                    "start": publisher.start(1),
                    "end": publisher.end(1),
                    "role": "publisher",
                    "context_span": {"start": 0, "end": len(text)},
                    "platform": "document",
                }
            )
            published = re.search(r"(?im)^Published at:\s*([^\r\n]+)$", text)
            if published:
                try:
                    timestamp = datetime.fromisoformat(published[1].strip().replace("Z", "+00:00"))
                    if timestamp.tzinfo is not None:
                        contexts[-1]["timestamp"] = timestamp.isoformat()
                except ValueError:
                    notices.append("INVALID_PUBLICATION_TIMESTAMP")
        safe = nh3.clean(
            tree.html or "",
            tags={
                "p",
                "div",
                "span",
                "br",
                "pre",
                "h1",
                "h2",
                "b",
                "strong",
                "em",
                "a",
                "ul",
                "li",
            },
            attributes={"a": {"href"}},
            url_schemes={"http", "https"},
        )
        derivatives.append(("HTML_SAFE", {"html": safe}))
    elif kind == "PDF":
        reader = PdfReader(io.BytesIO(data), strict=False)
        if reader.is_encrypted:
            return [], ["ENCRYPTED"]
        text = "\f".join(page.extract_text() or "" for page in reader.pages)
        if not text.strip():
            notices.append("TEXT_NOT_AVAILABLE")
    elif kind == "IMAGE":
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as img:
                if max(img.size) > 12000 or img.width * img.height > 80000000:
                    raise ValueError("IMAGE_SIZE_LIMIT")
                image_format = img.format or "UNKNOWN"
                exif = bool(img.getexif())
                oriented = ImageOps.exif_transpose(img)
                derivatives.append(
                    (
                        "IMAGE_META",
                        {
                            "width": oriented.width,
                            "height": oriented.height,
                            "format": image_format,
                            "exif_present": exif,
                            "phash": str(imagehash.phash(oriented)),
                            "dhash": str(imagehash.dhash(oriented)),
                        },
                    )
                )
        notices.append("OCR_UNAVAILABLE")
    elif kind == "JSON":
        obj = json.loads(decode(data))
        if isinstance(obj, dict) and isinstance(obj.get("messages"), list):
            messages = []
            for row in obj["messages"][:50000]:
                content = row.get("text", "")
                if isinstance(content, list):
                    content = "".join(
                        part if isinstance(part, str) else str(part.get("text", ""))
                        for part in content
                    )
                messages.append(
                    {
                        "id": str(row.get("id", len(messages))),
                        "sender": row.get("from"),
                        "text": str(content),
                        "at": row.get("date"),
                        "reply_to": str(row["reply_to_message_id"])
                        if row.get("reply_to_message_id")
                        else None,
                        "edited_at": row.get("edited"),
                        "media": [{"path": row[key]} for key in ("photo", "file") if row.get(key)],
                        "meta": {"system": row.get("type") != "message"},
                    }
                )
            derivatives.append(("MESSAGES", {"platform": "telegram", "messages": messages}))
            parts, offset = [], 0
            for message in messages:
                prefix = f"[{message['id']}] {message['at'] or ''} "
                line = prefix + f"{message['sender'] or ''}: {message['text']}"
                if message["sender"] and not message["meta"]["system"]:
                    contexts.append(
                        {
                            "value": message["sender"],
                            "start": offset + len(prefix),
                            "end": offset + len(prefix) + len(message["sender"]),
                            "role": "sender",
                            "context_span": {"start": offset, "end": offset + len(line)},
                            "platform": "telegram",
                            "message_id": message["id"],
                            "timestamp": message["at"],
                        }
                    )
                parts.append(line)
                offset += len(line) + 1
            text = "\n".join(parts)
        else:
            text = json.dumps(obj, ensure_ascii=False, indent=2)
            if isinstance(obj, list) and obj and all(isinstance(row, dict) for row in obj):
                header = list(dict.fromkeys(k for row in obj for k in row))[:64]
                rows = [[str(row.get(k, ""))[:2000] for k in header] for row in obj[:50000]]
                derivatives.append(
                    ("ROWS", {"header": header, "rows": rows, "truncated": len(obj) > 50000})
                )
    elif kind == "CSV":
        raw = decode(data)
        try:
            dialect = csv.Sniffer().sniff(raw[:8192])
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(io.StringIO(raw), dialect)
        header = next(reader, [])[:64]
        rows = []
        truncated = False
        for idx, row in enumerate(reader):
            if idx >= 50000:
                truncated = True
                break
            rows.append([value[:2000] for value in row[:64]])
        derivatives.append(("ROWS", {"header": header, "rows": rows, "truncated": truncated}))
        text = "\n".join(
            " · ".join(f"{header[i] if i < len(header) else i}: {v}" for i, v in enumerate(row))
            for row in rows
        )
        if any(v.startswith(("=", "+", "-", "@")) for row in rows for v in row):
            notices.append("FORMULA_STORED_AS_TEXT")
    elif kind == "TEXT":
        text = decode(data)
        pattern = re.compile(
            r"^(?:\[)?(\d{1,2}/\d{1,2}/\d{2,4}),\s*(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[apAP]\.?[mM]\.?)?)(?:\]\s*|\s*-\s*)(.*)$"
        )
        messages = []
        offset = 0
        for original_line in text.splitlines(keepends=True):
            line = original_line.rstrip("\r\n")
            match = pattern.match(line.replace("\u200e", "").replace("\u200f", ""))
            if match:
                if contexts:
                    contexts[-1]["context_span"]["end"] = offset
                sender, sep, content = match[3].partition(": ")
                timestamp = None
                raw_time = re.sub(r"\s+", " ", match[2].replace(".", "")).upper()
                for date_format in ("%d/%m/%Y", "%d/%m/%y"):
                    for time_format in ("%I:%M %p", "%I:%M:%S %p", "%H:%M", "%H:%M:%S"):
                        try:
                            timestamp = (
                                datetime.strptime(
                                    match[1] + " " + raw_time, date_format + " " + time_format
                                )
                                .replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))
                                .isoformat()
                            )
                            break
                        except ValueError:
                            continue
                    if timestamp:
                        break
                messages.append(
                    {
                        "id": str(len(messages) + 1),
                        "sender": sender if sep else None,
                        "text": content if sep else sender,
                        "at": timestamp,
                        "meta": {
                            "date_raw": match[1],
                            "time_raw": match[2],
                            "date_order": "DMY",
                            "system": not bool(sep),
                        },
                        "media": [{"path": "omitted"}] if "omitted" in content else [],
                    }
                )
                if sep and sender and sender in line:
                    start = offset + line.index(sender)
                    contexts.append(
                        {
                            "value": sender,
                            "start": start,
                            "end": start + len(sender),
                            "role": "sender",
                            "context_span": {"start": offset, "end": len(text)},
                            "platform": "whatsapp",
                            "message_id": str(len(messages)),
                            "timestamp": timestamp,
                        }
                    )
            elif messages:
                messages[-1]["text"] += "\n" + line
            offset += len(original_line)
        if messages:
            derivatives.append(("MESSAGES", {"platform": "whatsapp", "messages": messages}))
            notices.append("DATE_ORDER_ASSUMED_DMY")
    elif kind == "AUDIO":
        notices.append("TRANSCRIPT_PENDING")
    else:
        notices.append("PARSER_UNAVAILABLE")
    if text:
        derivatives.append(("TEXT", text_doc(text, contexts)))
    return derivatives, notices
