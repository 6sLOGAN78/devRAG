"""Bounded inert MIME decoding; plain alternatives win and attachments are never executed."""

from email import policy
from email.errors import CloseBoundaryNotFoundDefect, NoBoundaryInMultipartDefect, StartBoundaryNotFoundDefect
from email.header import decode_header
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
import re

from rag.parsers.email_types import EmailEnvelope, IgnoredAttachment
from rag.parsers.errors import FileDamaged, FileTooLarge, NoReadableText
from rag.parsers.html import parse_markup
from rag.parsers.types import ParsedBlock

MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_DECODED_BYTES = 1024 * 1024
MAX_PARTS = 128
MAX_DEPTH = 16
MAX_HEADER = 2048
_FATAL = (CloseBoundaryNotFoundDefect, NoBoundaryInMultipartDefect, StartBoundaryNotFoundDefect)


def _decoded_header(value):
    if len(value) > MAX_HEADER * 4:
        raise FileTooLarge()
    try:
        parts = [part.decode(charset or "utf-8") if isinstance(part, bytes) else part for part, charset in decode_header(value)]
        text = "".join(parts).encode("utf-8", errors="surrogateescape").decode("utf-8")
    except (LookupError, UnicodeError, ValueError):
        raise FileDamaged() from None
    if len(text) > MAX_HEADER:
        raise FileTooLarge()
    if any(ord(c) < 32 and c not in "\r\n\t" for c in text):
        raise FileDamaged()
    return " ".join(text.split())


def _header(message, name):
    return ", ".join(_decoded_header(value) for key, value in message.raw_items() if key.lower() == name.lower())


def _attachment(part):
    return part.get_content_disposition() == "attachment" or part.get_filename() is not None or (not part.is_multipart() and part.get_content_type() not in {"text/plain", "text/html"}) or part.get_content_maintype() == "message"


def _selected(part, path="1"):
    if _attachment(part):
        return []
    if not part.is_multipart():
        return [(part, path)] if part.get_content_type() in {"text/plain", "text/html"} else []
    children = list(part.iter_parts())
    if part.get_content_subtype() == "related":
        start = part.get_param("start")
        chosen = next((i for i, child in enumerate(children) if start and child.get("Content-ID") == start), 0)
        return _selected(children[chosen], f"{path}.{chosen + 1}") if children else []
    groups = [_selected(child, f"{path}.{i}") for i, child in enumerate(children, 1)]
    if part.get_content_subtype() == "alternative":
        for kind in ("text/plain", "text/html"):
            for group in groups:
                candidates = [(child, source) for child, source in group if child.get_content_type() == kind]
                if candidates:
                    return candidates
        return []
    return [item for group in groups for item in group]


def parse(source, report, *, page_range=None, limits=None):
    cap = min(MAX_SOURCE_BYTES, limits.max_text_bytes) if limits else MAX_SOURCE_BYTES
    try:
        with source.path.open("rb") as stream:
            data = stream.read(cap + 1)
    except OSError:
        raise FileDamaged() from None
    if len(data) > cap:
        raise FileTooLarge()
    count = 0

    def message_factory(*args, **kwargs):
        nonlocal count
        count += 1
        if count > MAX_PARTS:
            raise FileTooLarge()
        return EmailMessage(*args, **kwargs)

    try:
        message = BytesParser(policy=policy.default.clone(message_factory=message_factory)).parsebytes(data)
        stack = [(message, "1", 0)]
        attachments = []
        while stack:
            part, path, depth = stack.pop()
            if depth > MAX_DEPTH:
                raise FileTooLarge()
            headers = list(part.raw_items())
            if len(headers) > 128 or any(len(value) > MAX_HEADER * 4 for _, value in headers):
                raise FileTooLarge()
            declared = [value for key, value in headers if key.lower() == "content-type"]
            if len(declared) > 1 or (declared and not re.fullmatch(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+", declared[0].split(";", 1)[0].strip())):
                raise FileDamaged()
            if sum(key.lower() == "content-transfer-encoding" for key, _ in headers) > 1:
                raise FileDamaged()
            if any(isinstance(defect, _FATAL) for defect in part.defects):
                raise FileDamaged()
            if _attachment(part):
                name = _decoded_header(part.get_filename() or "")
                if len(name) > 255:
                    raise FileTooLarge()
                attachments.append(IgnoredAttachment(name, part.get_content_type(), path))
            if part.is_multipart():
                stack.extend((child, f"{path}.{i}", depth + 1) for i, child in reversed(list(enumerate(part.get_payload(), 1))))
        sender, to, subject, date, message_id = (_header(message, key) for key in ("From", "To", "Subject", "Date", "Message-ID"))
        recipients = tuple(dict.fromkeys(address for _, address in getaddresses([to]) if address))
        if len(recipients) > 64:
            raise FileTooLarge()
        if date:
            try:
                if parsedate_to_datetime(date) is None:
                    raise ValueError
            except (ValueError, TypeError, OverflowError):
                report.add_note("The date header could not be interpreted; its original value was retained.")
        if attachments:
            report.add_note(f"Ignored {len(attachments)} attachment(s); attachments were not parsed or executed.")
        blocks, decoded_bytes = [], 0
        for part, path in _selected(message):
            transfer = str(part.get("Content-Transfer-Encoding", "7bit")).strip().lower()
            if transfer not in {"7bit", "8bit", "binary", "base64", "quoted-printable"}:
                raise FileDamaged()
            if transfer == "quoted-printable" and re.search(r"=(?![0-9A-Fa-f]{2}|\r?\n)", str(part.get_payload())):
                raise FileDamaged()
            payload = part.get_payload(decode=True)
            if not isinstance(payload, bytes) or any(type(defect).__name__.startswith("InvalidBase64") for defect in part.defects):
                raise FileDamaged()
            decoded_bytes += len(payload)
            if decoded_bytes > min(cap, MAX_DECODED_BYTES):
                raise FileTooLarge()
            text = payload.decode(part.get_content_charset() or "ascii").replace("\r\n", "\n").replace("\r", "\n")
            if "\0" in text:
                raise FileDamaged()
            if part.get_content_type() == "text/html":
                try:
                    text = "\n".join(block.text for block in parse_markup(text.encode("utf-8")))
                except NoReadableText:
                    continue
            if text.strip():
                envelope = EmailEnvelope(sender, recipients, subject, date, message_id, path, tuple(attachments))
                blocks.append(ParsedBlock(text, email=envelope))
    except (UnicodeError, LookupError, ValueError, TypeError, RecursionError, IndexError):
        raise FileDamaged() from None
    if not blocks:
        raise NoReadableText()
    return iter(blocks)
