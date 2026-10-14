"""Relational audit schema, independent from domain model definitions."""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

users = Table(
    "user_accounts",
    metadata,
    Column("user_id", String, primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("length(trim(user_id)) > 0", name="user_id_nonempty"),
)
devices = Table(
    "devices",
    metadata,
    Column("device_id", String, primary_key=True),
    Column("first_seen_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("length(trim(device_id)) > 0", name="device_id_nonempty"),
)
transactions = Table(
    "transactions",
    metadata,
    Column("transaction_id", String, primary_key=True),
    Column("user_id", String, ForeignKey("user_accounts.user_id"), nullable=False),
    Column("merchant_id", String, nullable=False),
    Column("amount_minor", BigInteger, nullable=False),
    Column("currency", String(3), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("amount_minor >= 0", name="amount_nonnegative"),
    CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_uppercase"),
    CheckConstraint("length(trim(merchant_id)) > 0", name="merchant_id_nonempty"),
)
payments = Table(
    "payment_attempts",
    metadata,
    Column("payment_id", String, primary_key=True),
    Column(
        "transaction_id",
        String,
        ForeignKey("transactions.transaction_id"),
        nullable=False,
    ),
    Column("attempted_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("payment_id", "transaction_id", name="uq_payment_transaction"),
)
decisions = Table(
    "decisions",
    metadata,
    Column("decision_id", String, primary_key=True),
    Column(
        "subject_id", String, ForeignKey("transactions.transaction_id"), nullable=False
    ),
    Column("payment_id", String, nullable=False),
    Column("action", String, nullable=False),
    Column("decided_at", DateTime(timezone=True), nullable=False),
    Column("policy_id", String, nullable=False),
    Column("policy_version", Integer, nullable=False),
    Column("rule_set_id", String, nullable=False),
    Column("rule_set_version", Integer, nullable=False),
    ForeignKeyConstraint(
        ["payment_id", "subject_id"],
        ["payment_attempts.payment_id", "payment_attempts.transaction_id"],
    ),
    CheckConstraint(
        "action IN ('ALLOW','CHALLENGE','REVIEW','BLOCK')", name="action_valid"
    ),
    CheckConstraint(
        "policy_version > 0 AND rule_set_version > 0", name="versions_positive"
    ),
    CheckConstraint(
        "length(trim(policy_id)) > 0 AND length(trim(rule_set_id)) > 0",
        name="provenance_nonempty",
    ),
)
decision_idempotency = Table(
    "decision_idempotency",
    metadata,
    Column("idempotency_key", String(255), primary_key=True),
    Column("request_fingerprint", String(64), nullable=False),
    Column(
        "decision_id",
        String,
        ForeignKey("decisions.decision_id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    ),
)
reasons = Table(
    "decision_reasons",
    metadata,
    Column(
        "decision_id",
        String,
        ForeignKey("decisions.decision_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("ordinal", Integer, nullable=False),
    Column("reason_code", String, nullable=False),
    PrimaryKeyConstraint("decision_id", "ordinal"),
    CheckConstraint("ordinal >= 0", name="reason_ordinal_nonnegative"),
    CheckConstraint("length(trim(reason_code)) > 0", name="reason_nonempty"),
)
decision_devices = Table(
    "decision_devices",
    metadata,
    Column(
        "decision_id",
        String,
        ForeignKey("decisions.decision_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("ordinal", Integer, nullable=False),
    Column("device_id", String, ForeignKey("devices.device_id"), nullable=False),
    PrimaryKeyConstraint("decision_id", "ordinal"),
    CheckConstraint("ordinal >= 0", name="device_ordinal_nonnegative"),
)


def signal_columns():
    return (
        Column("code", String, nullable=False),
        Column("value_type", String, nullable=False),
        Column("value", JSONB, nullable=False),
        Column("observed_at", DateTime(timezone=True), nullable=False),
        Column("source", String, nullable=False),
        CheckConstraint(
            "value_type IN ('bool','int','float','str')", name="signal_type_valid"
        ),
        CheckConstraint(
            "length(trim(code)) > 0 AND length(trim(source)) > 0",
            name="signal_identity_nonempty",
        ),
    )


signals = Table(
    "decision_risk_signals",
    metadata,
    Column(
        "decision_id",
        String,
        ForeignKey("decisions.decision_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("ordinal", Integer, nullable=False),
    *signal_columns(),
    PrimaryKeyConstraint("decision_id", "ordinal"),
    CheckConstraint("ordinal >= 0", name="signal_ordinal_nonnegative"),
)
evaluations = Table(
    "rule_evaluations",
    metadata,
    Column(
        "decision_id",
        String,
        ForeignKey("decisions.decision_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("ordinal", Integer, nullable=False),
    Column("rule_id", String, nullable=False),
    Column("rule_version", Integer, nullable=False),
    Column("status", String, nullable=False),
    Column("recommended_action", String),
    Column("reason_code", String),
    Column("diagnostic", String),
    PrimaryKeyConstraint("decision_id", "ordinal"),
    UniqueConstraint("decision_id", "rule_id", "rule_version", name="uq_decision_rule"),
    CheckConstraint(
        "ordinal >= 0 AND rule_version > 0", name="rule_position_version_valid"
    ),
    CheckConstraint(
        "status IN ('MATCHED','NOT_MATCHED','INDETERMINATE')", name="rule_status_valid"
    ),
    CheckConstraint(
        "recommended_action IS NULL OR recommended_action IN "
        "('ALLOW','CHALLENGE','REVIEW','BLOCK')",
        name="rule_action_valid",
    ),
)
evidence = Table(
    "rule_evaluation_evidence",
    metadata,
    Column("decision_id", String, nullable=False),
    Column("evaluation_ordinal", Integer, nullable=False),
    Column("evidence_ordinal", Integer, nullable=False),
    *signal_columns(),
    PrimaryKeyConstraint("decision_id", "evaluation_ordinal", "evidence_ordinal"),
    ForeignKeyConstraint(
        ["decision_id", "evaluation_ordinal"],
        ["rule_evaluations.decision_id", "rule_evaluations.ordinal"],
        ondelete="CASCADE",
    ),
    CheckConstraint("evidence_ordinal >= 0", name="evidence_ordinal_nonnegative"),
)
