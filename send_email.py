from __future__ import annotations

import argparse
import mimetypes
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path


DEFAULT_TO = "dideum@naver.com"


def getenv_required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"필수 환경변수 {name} 값이 비어 있습니다.")
    return value


def as_bool(value: str, default: bool = True) -> bool:
    if value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def latest_file_from_output_dir() -> Path:
    """ZIP이 있으면 ZIP을, 없으면 최신 CSV를 반환."""
    output_dir = Path("output")
    zips = sorted(output_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    if zips:
        return zips[0]
    files = sorted(output_dir.glob("**/*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError("output 디렉터리에서 ZIP 또는 CSV 파일을 찾지 못했습니다.")
    return files[0]


def build_message(attachment_path: Path) -> EmailMessage:
    smtp_username = getenv_required("SMTP_USERNAME")
    from_addr = os.getenv("SMTP_FROM", smtp_username).strip() or smtp_username
    to_addr = os.getenv("SMTP_TO", DEFAULT_TO).strip() or DEFAULT_TO
    subject = os.getenv("EMAIL_SUBJECT", f"G마켓 베스트 크롤링 결과 - {datetime.now():%Y-%m-%d}").strip()

    message = EmailMessage()
    message["From"] = from_addr
    message["To"] = to_addr
    message["Subject"] = subject
    message.set_content(
        "안녕하세요.\n\n"
        "GitHub Actions에서 실행한 G마켓 베스트 전 카테고리(47개) 크롤링 결과를 첨부합니다.\n\n"
        f"첨부 파일: {attachment_path.name}\n"
        f"생성 시각: {datetime.now():%Y-%m-%d %H:%M:%S}\n\n"
        "※ ZIP 파일 내 카테고리별 CSV와 전체 합본 CSV(ALL)가 포함되어 있습니다.\n\n"
        "이 메일은 자동 발송되었습니다."
    )

    ctype, encoding = mimetypes.guess_type(str(attachment_path))
    if ctype is None or encoding is not None:
        maintype, subtype = "application", "octet-stream"
    else:
        maintype, subtype = ctype.split("/", 1)

    with attachment_path.open("rb") as f:
        message.add_attachment(f.read(), maintype=maintype, subtype=subtype, filename=attachment_path.name)
    return message


def send_message(message: EmailMessage) -> None:
    host = getenv_required("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    password = getenv_required("SMTP_PASSWORD")
    username = getenv_required("SMTP_USERNAME")
    use_tls = as_bool(os.getenv("SMTP_USE_TLS", "true"), default=True)
    use_ssl = as_bool(os.getenv("SMTP_USE_SSL", "false"), default=False)

    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=60) as server:
            server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=60) as server:
            server.ehlo()
            if use_tls:
                server.starttls()
                server.ehlo()
            server.login(username, password)
            server.send_message(message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CSV 파일을 SMTP 이메일 첨부로 발송합니다.")
    parser.add_argument("--file", default="", help="발송할 CSV 경로. 미지정 시 output/*.csv 중 최신 파일")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    attachment_path = Path(args.file) if args.file else latest_file_from_output_dir()
    if not attachment_path.exists():
        raise FileNotFoundError(f"첨부 파일을 찾을 수 없습니다: {attachment_path}")

    message = build_message(attachment_path)
    send_message(message)
    print(f"email_sent_to={message['To']}")
    print(f"attachment={attachment_path}")


if __name__ == "__main__":
    main()
