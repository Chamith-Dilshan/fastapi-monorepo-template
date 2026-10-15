from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.core.email.base import EmailSender, get_email_sender
from app.core.email.console_sender import ConsoleEmailSender
from app.core.email.resend_sender import ResendEmailSender
from app.core.email.smtp_sender import SmtpEmailSender
from app.emails.renderer import render_template
from app.models.otp_code import OTPPurpose
from app.services.email_service import EmailService


class SpySender(EmailSender):
    def __init__(self):
        self.sent: list[dict] = []

    async def send(self, *, to, subject, html_body):
        self.sent.append({"to": to, "subject": subject, "html": html_body})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("purpose", "subject"),
    [
        (OTPPurpose.EMAIL_VERIFICATION, "Verify your email"),
        (OTPPurpose.PASSWORD_RESET, "Reset your password"),
        (OTPPurpose.TWO_FACTOR, "Your sign-in code"),
    ],
)
async def test_otp_email_has_the_right_subject_and_contains_the_code(purpose, subject):
    spy = SpySender()
    await EmailService(spy).send_otp_code(
        to="a@example.com", purpose=purpose, code="482913"
    )
    assert spy.sent[0]["subject"] == subject
    assert "482913" in spy.sent[0]["html"]
    assert spy.sent[0]["to"] == "a@example.com"


@pytest.mark.asyncio
async def test_welcome_email_greets_by_name():
    spy = SpySender()
    await EmailService(spy).send_welcome_email(to="a@example.com", first_name="Ada")
    assert "Hi Ada" in spy.sent[0]["html"]


def test_templates_escape_html_in_user_supplied_values():
    html = render_template(
        "welcome.html", app_name="App", first_name="<script>alert(1)</script>"
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


@pytest.mark.asyncio
async def test_console_sender_sends_nothing_and_does_not_fail():
    await ConsoleEmailSender().send(
        to="a@example.com", subject="s", html_body="<p>x</p>"
    )


def test_provider_setting_picks_the_sender(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "console")
    assert isinstance(get_email_sender(), ConsoleEmailSender)

    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "resend")
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
    assert isinstance(get_email_sender(), ResendEmailSender)


@pytest.mark.asyncio
async def test_resend_sender_builds_the_expected_request(monkeypatch):
    send = AsyncMock(return_value={"id": "1"})
    monkeypatch.setattr("resend.Emails.send_async", send)
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
    monkeypatch.setattr(settings, "EMAIL_FROM_NAME", "My App")
    monkeypatch.setattr(settings, "EMAIL_FROM_ADDRESS", "hello@example.com")

    await ResendEmailSender().send(
        to="a@example.com", subject="Hi", html_body="<p>x</p>"
    )

    send.assert_awaited_once_with(
        {
            "from": "My App <hello@example.com>",
            "to": ["a@example.com"],
            "subject": "Hi",
            "html": "<p>x</p>",
        }
    )


@pytest.mark.asyncio
async def test_resend_failures_propagate_to_the_caller(monkeypatch):
    monkeypatch.setattr(
        "resend.Emails.send_async", AsyncMock(side_effect=RuntimeError("down"))
    )
    monkeypatch.setattr(settings, "RESEND_API_KEY", "re_test")
    with pytest.raises(RuntimeError, match="down"):
        await ResendEmailSender().send(to="a@example.com", subject="s", html_body="x")


# --- SMTP -------------------------------------------------------------------


@pytest.fixture
def smtp_settings(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_USER", "user")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "pass")
    monkeypatch.setattr(settings, "SMTP_TLS", True)
    monkeypatch.setattr(settings, "SMTP_SSL", False)
    monkeypatch.setattr(settings, "EMAIL_FROM_NAME", "My App")
    monkeypatch.setattr(settings, "EMAIL_FROM_ADDRESS", "hello@example.com")


@pytest.mark.asyncio
async def test_smtp_sender_builds_a_multipart_message(monkeypatch, smtp_settings):
    send = AsyncMock()
    monkeypatch.setattr("aiosmtplib.send", send)

    await SmtpEmailSender().send(
        to="a@example.com",
        subject="Hi",
        html_body="<style>p{color:red}</style><p>Your code is <b>123456</b> &amp; more</p>",
    )

    call = send.await_args
    assert call is not None
    message = call.args[0]
    assert message["From"] == "My App <hello@example.com>"
    assert message["To"] == "a@example.com"
    assert message["Subject"] == "Hi"
    text_part = message.get_body(preferencelist=("plain",)).get_content()
    html_part = message.get_body(preferencelist=("html",)).get_content()
    assert "Your code is 123456 & more" in text_part
    assert "color:red" not in text_part
    assert "<b>123456</b>" in html_part


@pytest.mark.asyncio
async def test_smtp_sender_passes_connection_settings(monkeypatch, smtp_settings):
    send = AsyncMock()
    monkeypatch.setattr("aiosmtplib.send", send)

    await SmtpEmailSender().send(to="a@example.com", subject="s", html_body="<p>x</p>")

    call = send.await_args
    assert call is not None
    kwargs = call.kwargs
    assert kwargs["hostname"] == "smtp.example.com"
    assert kwargs["port"] == 587
    assert (kwargs["username"], kwargs["password"]) == ("user", "pass")
    assert kwargs["start_tls"] is True
    assert kwargs["use_tls"] is False


@pytest.mark.asyncio
async def test_smtp_failures_propagate_to_the_caller(monkeypatch, smtp_settings):
    monkeypatch.setattr("aiosmtplib.send", AsyncMock(side_effect=OSError("refused")))
    with pytest.raises(OSError, match="refused"):
        await SmtpEmailSender().send(to="a@example.com", subject="s", html_body="x")


def test_provider_setting_can_select_smtp(monkeypatch, smtp_settings):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "smtp")
    assert isinstance(get_email_sender(), SmtpEmailSender)
