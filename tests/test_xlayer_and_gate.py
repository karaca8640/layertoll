import time
from decimal import Decimal

import pytest
from x402.mechanisms.evm.exact.server import ExactEvmScheme

from services.agentpay.onchain import ERC20_TRANSFER_TOPIC, verify_settlement_transfer
from services.agentpay.settings import load_settings
from services.agentpay.x402_gate import InMemoryReplayLedger, PaymentError, PaymentGate, replay_key_for
from services.agentpay.xlayer import XLAYER_MAINNET, XLAYER_TESTNET, get_network, is_evm_address
from tests.conftest import SELLER_WALLET, sign_payment


def test_xlayer_network_constants():
    assert XLAYER_MAINNET.chain_id == 196 and XLAYER_MAINNET.caip2 == "eip155:196"
    assert XLAYER_TESTNET.chain_id == 1952 and XLAYER_TESTNET.caip2 == "eip155:1952"
    assert XLAYER_MAINNET.payment_asset.address == "0x779Ded0c9e1022225f8E0630b35a9b54bE713736"
    assert XLAYER_TESTNET.payment_asset.address == "0x9e29b3aada05bf2d2c827af80bd28dc0b9b4fb0c"
    for net in (XLAYER_MAINNET, XLAYER_TESTNET):
        assert net.payment_asset.decimals == 6
        assert net.payment_asset.eip712_name == "USD₮0" and net.payment_asset.eip712_version == "1"
        assert net.native_gas_token == "OKB"
        assert net.rpc_url.startswith("https://") and net.explorer_url.startswith("https://www.oklink.com/")
    assert XLAYER_MAINNET.tx_url("0xabc") == "https://www.oklink.com/xlayer/tx/0xabc"
    assert XLAYER_MAINNET.to_atomic(Decimal("0.01")) == 10_000
    assert XLAYER_MAINNET.from_atomic(5000) == Decimal("0.005")


def test_network_selection_from_env(monkeypatch):
    monkeypatch.setenv("AGENTPAY_NETWORK", "xlayer-testnet")
    assert get_network().chain_id == 1952
    monkeypatch.setenv("XLAYER_RPC_URL", "https://rpc.example.test")
    assert get_network().rpc_url == "https://rpc.example.test"
    monkeypatch.setenv("AGENTPAY_NETWORK", "ethereum")
    with pytest.raises(ValueError):
        get_network()


def test_mainnet_asset_matches_official_sdk_defaults():
    """Our X Layer config must agree with the OKX Payments SDK's built-in asset table."""
    sdk = ExactEvmScheme()._default_money_conversion("$0.01", "eip155:196")
    gate = PaymentGate(XLAYER_MAINNET, facilitator=None, ledger=InMemoryReplayLedger())
    req = gate.requirements_for(Decimal("0.01"), SELLER_WALLET)
    assert req.asset == sdk.asset.lower()
    assert req.amount == sdk.amount == "10000"
    assert req.extra == sdk.extra


def test_evm_address_validation():
    assert is_evm_address(SELLER_WALLET)
    for bad in (None, "", "0x123", "1111111111111111111111111111111111111111", "0x" + "g" * 40):
        assert not is_evm_address(bad)


def test_public_status_never_contains_secrets(monkeypatch):
    monkeypatch.setenv("OKX_API_KEY", "okx-key-123456")
    monkeypatch.setenv("OKX_SECRET_KEY", "okx-secret-abcdef")
    monkeypatch.setenv("OKX_PASSPHRASE", "okx-pass-xyz")
    settings = load_settings()
    assert settings.facilitator_configured
    blob = repr(settings.public_status())
    for secret in ("okx-key-123456", "okx-secret-abcdef", "okx-pass-xyz"):
        assert secret not in blob


async def test_gate_rejects_expired_and_mismatched_payments(buyer, facilitator):
    gate = PaymentGate(XLAYER_MAINNET, facilitator=facilitator, ledger=InMemoryReplayLedger())
    req = gate.requirements_for(Decimal("0.01"), SELLER_WALLET)
    payload = await sign_payment(buyer[1], gate.payment_required(req, "https://x/y", "t"))

    expired = payload.model_copy(deep=True)
    expired.payload["authorization"]["validBefore"] = str(int(time.time()) - 5)
    with pytest.raises(PaymentError) as exc:
        await gate.verify(expired, req)
    assert exc.value.code == "payment_expired"

    other_network = gate.requirements_for(Decimal("0.01"), SELLER_WALLET).model_copy(update={"network": "eip155:8453"})
    with pytest.raises(PaymentError) as exc:
        await gate.verify(payload, other_network)
    assert exc.value.code == "payment_requirements_mismatch"
    assert facilitator.verify_calls == 0  # rejected locally, before the facilitator

    verified = await gate.verify(payload, req)
    assert verified.replay_key == replay_key_for(payload)
    assert verified.replay_key.startswith("eip155:196:" + buyer[0].address.lower())


def test_v1_payloads_are_refused():
    with pytest.raises(PaymentError) as exc:
        PaymentGate.decode_object({"x402Version": 1, "scheme": "exact", "network": "base", "payload": {}})
    assert exc.value.code in ("invalid_payment_payload", "unsupported_x402_version")


def _receipt(to: str, amount: int, asset: str = XLAYER_MAINNET.payment_asset.address, status: str = "0x1"):
    pad = lambda a: "0x" + "0" * 24 + a[2:].lower()  # noqa: E731
    return {
        "status": status,
        "blockNumber": "0x10",
        "logs": [
            {
                "address": asset,
                "topics": [ERC20_TRANSFER_TOPIC, pad("0x" + "a" * 40), pad(to)],
                "data": hex(amount),
            }
        ],
    }


async def test_onchain_settlement_check():
    tx = "0x" + "ab" * 32

    def rpc(receipt):
        async def call(method, params):
            assert method == "eth_getTransactionReceipt" and params == [tx]
            return receipt

        return call

    ok = await verify_settlement_transfer(XLAYER_MAINNET, tx, SELLER_WALLET, 5000, rpc_call=rpc(_receipt(SELLER_WALLET, 5000)))
    assert ok.verified and ok.block_number == 16 and ok.amount_atomic == 5000

    for receipt, reason in [
        (_receipt(SELLER_WALLET, 4999), "matching_transfer_not_found"),
        (_receipt("0x" + "2" * 40, 5000), "matching_transfer_not_found"),
        (_receipt(SELLER_WALLET, 5000, asset="0x" + "3" * 40), "matching_transfer_not_found"),
        (_receipt(SELLER_WALLET, 5000, status="0x0"), "transaction_reverted"),
        (None, "receipt_not_found"),
    ]:
        check = await verify_settlement_transfer(XLAYER_MAINNET, tx, SELLER_WALLET, 5000, rpc_call=rpc(receipt))
        assert not check.verified and check.reason == reason

    bad = await verify_settlement_transfer(XLAYER_MAINNET, "not-a-hash", SELLER_WALLET, 1)
    assert not bad.verified
