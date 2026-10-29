"""Decoded email envelope and actual MIME-part provenance, independent of page geometry."""

from dataclasses import dataclass


@dataclass(frozen=True)
class IgnoredAttachment:
    name: str
    content_type: str
    part_path: str


@dataclass(frozen=True)
class EmailEnvelope:
    sender: str
    recipients: tuple[str, ...]
    subject: str
    date: str
    message_id: str
    part_path: str
    attachments: tuple[IgnoredAttachment, ...] = ()

    def prefix(self) -> str:
        lines = [f"From: {self.sender}", f"To: {', '.join(self.recipients)}", f"Subject: {self.subject}", f"Date: {self.date}"]
        if self.message_id:
            lines.append(f"Message-ID: {self.message_id}")
        lines.append(f"MIME part: {self.part_path}")
        lines.extend(f"Ignored attachment: {a.name or '(unnamed)'} ({a.content_type}; part {a.part_path})" for a in self.attachments)
        return "\n".join(lines) + "\n\n"
