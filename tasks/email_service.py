from django.conf import settings
from django.core.mail import send_mail

PLACEHOLDERS = {
    "",
    "(add recipient)",
    "add recipient",
    "todo",
    "tbd",
}


class EmailDraftError(ValueError):
    pass


def parse_email_draft(draft_content):
    to = ""
    subject = ""
    body_lines = []
    in_body = False

    for line in (draft_content or "").splitlines():
        if not in_body:
            lower = line.lower()
            if lower.startswith("to:"):
                to = line.split(":", 1)[1].strip()
                continue
            if lower.startswith("subject:"):
                subject = line.split(":", 1)[1].strip()
                continue
            if line.strip() == "":
                in_body = True
                continue
            body_lines.append(line)
        else:
            body_lines.append(line)

    return to, subject, "\n".join(body_lines).strip()


def set_to_line(draft_content, recipient):
    recipient = (recipient or "").strip()
    if not recipient:
        return draft_content or ""
    lines = (draft_content or "").splitlines()
    replaced = False
    out = []
    for line in lines:
        if not replaced and line.lower().startswith("to:"):
            out.append(f"To: {recipient}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.insert(0, f"To: {recipient}")
    return "\n".join(out)


def send_action_email(draft_content):
    to, subject, body = parse_email_draft(draft_content)
    if to.lower() in PLACEHOLDERS or "@" not in to:
        raise EmailDraftError(
            "Edit the draft and put a real address on the To: line before you approve."
        )
    if not subject:
        raise EmailDraftError("Edit the draft and add a Subject: line before you approve.")
    if not body:
        body = subject

    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to],
        fail_silently=False,
    )
    return {
        "to": to,
        "subject": subject,
        "backend": settings.EMAIL_BACKEND,
    }