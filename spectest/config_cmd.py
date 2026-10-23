"""`spectest config`: open, locate, and check the shared settings file (API keys, SMTP)."""
import os
import shutil
import subprocess
import sys
from email.mime.text import MIMEText

from dotenv import load_dotenv

from spectest.config import GLOBAL_ENV, migrate_global_env
from spectest.tools import llm_bridge, notifier


def ensure_file():
    migrate_global_env()
    if not GLOBAL_ENV.exists():
        from spectest.scaffold import ENV_TEMPLATE
        GLOBAL_ENV.parent.mkdir(parents=True, exist_ok=True)
        GLOBAL_ENV.write_text(ENV_TEMPLATE, encoding="utf-8")


def open_in_editor():
    if os.getenv("EDITOR"):
        subprocess.run([os.environ["EDITOR"], str(GLOBAL_ENV)])
    elif sys.platform == "win32":
        subprocess.Popen(["notepad.exe", str(GLOBAL_ENV)])  # .env has no default app on Windows
    elif sys.platform == "darwin":
        subprocess.run(["open", "-t", str(GLOBAL_ENV)])
    elif shutil.which("xdg-open"):
        subprocess.run(["xdg-open", str(GLOBAL_ENV)])
    else:
        print(f"Edit this file: {GLOBAL_ENV}")


def check() -> bool:
    """Ping every configured LLM provider and log in to SMTP (without sending). Returns True if usable."""
    load_dotenv(GLOBAL_ENV, override=True)
    ok_llm = False
    for name, base_url, key_var, model_var, default_model in llm_bridge.PROVIDERS:
        model = os.getenv(model_var) or default_model
        if not os.getenv(key_var):
            print(f"  {name:<11} not configured ({key_var} empty)")
            continue
        try:
            client = llm_bridge.OpenAI(base_url=base_url, api_key=os.getenv(key_var), timeout=30, max_retries=0)
            client.chat.completions.create(model=model, messages=[{"role": "user", "content": "Reply: ok"}],
                                           max_tokens=5)
            print(f"  {name:<11} OK ({model})")
            ok_llm = True
        except Exception as e:
            print(f"  {name:<11} FAILED ({model}): {type(e).__name__}: {str(e)[:160]}")

    if not os.getenv("SMTP_USER"):
        print("  email       not configured (reports are saved to .spectest/outbox/)")
    else:
        try:
            host, port, user, password = notifier.smtp_settings()
            notifier.smtp_login(user, password, host, port).quit()
            print(f"  email       OK (logged in to {host}:{port} as {user})")
        except Exception as e:
            print(f"  email       FAILED: {e}")
    if not ok_llm:
        print("  -> no working LLM provider: add at least one API key.")
    return ok_llm


def send_test_email(to_addr: str | None) -> bool:
    load_dotenv(GLOBAL_ENV, override=True)
    to_addr = to_addr or os.getenv("SMTP_USER", "")
    msg = MIMEText("This is a test email from SpecTest. If you can read it, email reports are set up correctly.\n",
                   "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = "[SpecTest] Test email", os.getenv("SMTP_USER", ""), to_addr
    try:
        notifier.send_smtp(msg)
    except Exception as e:
        print(f"  FAILED: {e}")
        return False
    print(f"  sent a test email to {to_addr}; check that inbox (and spam).")
    return True


def run(args) -> int:
    ensure_file()
    if args.path:
        print(GLOBAL_ENV)
        return 0
    if args.check or args.test_email is not None:
        print(f"Settings: {GLOBAL_ENV}")
        ok = check()
        if args.test_email is not None:
            ok = send_test_email(args.test_email or None) and ok
        return 0 if ok else 1
    print(f"Opening {GLOBAL_ENV}")
    print("After saving, run `spectest config --check` to verify your keys.")
    open_in_editor()
    return 0
