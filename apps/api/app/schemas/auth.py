import re

from pydantic import BaseModel, EmailStr, Field, model_validator


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)

    @model_validator(mode="after")
    def strong_password(self) -> "RegisterRequest":
        if not re.search(r"[A-Z]", self.password):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"\d", self.password):
            raise ValueError("Password must contain at least one digit")
        return self


class LoginRequest(BaseModel):
    """Accepts either (email + password) OR (wallet_address + signature).

    Exactly one login method must be provided.
    """

    # ── Password login ────────────────────────────────────────────────────
    email: EmailStr | None = None
    password: str | None = None

    # ── Web3 wallet login ─────────────────────────────────────────────────
    wallet_address: str | None = Field(
        None, pattern=r"^0x[0-9a-fA-F]{40}$", description="EVM wallet address (0x…)"
    )
    signature: str | None = Field(
        None, description="EIP-191 personal_sign of the nonce message"
    )

    @model_validator(mode="after")
    def exactly_one_method(self) -> "LoginRequest":
        has_pw = bool(self.email and self.password)
        has_wallet = bool(self.wallet_address and self.signature)
        if has_pw == has_wallet:  # both true or both false
            raise ValueError(
                "Provide exactly one login method: "
                "(email + password) or (wallet_address + signature)"
            )
        return self

    @property
    def is_wallet_login(self) -> bool:
        return bool(self.wallet_address and self.signature)


class NonceRequest(BaseModel):
    wallet_address: str = Field(..., pattern=r"^0x[0-9a-fA-F]{40}$")


class NonceResponse(BaseModel):
    wallet_address: str
    nonce: str
    message: str        # full string the client must sign
    expires_in: int     # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int     # seconds until access_token expiry


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    wallet_address: str | None = None
    is_active: bool

    model_config = {"from_attributes": True}
