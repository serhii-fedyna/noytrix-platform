from sqlalchemy import Column, Integer, String, DateTime, Text, UniqueConstraint
from datetime import datetime
from db import Base

class IAPPurchase(Base):
    __tablename__ = "iap_purchases"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)

    provider = Column(String, default="google", nullable=False)  # google
    product_type = Column(String, nullable=False)               # subs | inapp
    product_id = Column(String, nullable=False)
    package_name = Column(String, nullable=False)

    purchase_token = Column(String, nullable=False, unique=True)
    status = Column(String, default="active", nullable=False)    # active | expired | canceled | unknown
    expiry_time_utc = Column(DateTime, nullable=True)

    # ===== extra safety fields (2nd level protection) =====
    order_id = Column(String, nullable=True)                     # Google orderId
    purchase_time_utc = Column(DateTime, nullable=True)          # purchaseTimeMillis -> UTC naive
    linked_purchase_token = Column(String, nullable=True)        # linkedPurchaseToken (upgrade/downgrade)
    acknowledgement_state = Column(Integer, nullable=True)       # 0/1
    payment_state = Column(Integer, nullable=True)               # subs paymentState
    cancel_reason = Column(Integer, nullable=True)               # subs cancelReason
    purchase_state = Column(Integer, nullable=True)              # inapp purchaseState

    raw = Column(Text, nullable=True)  # JSON string
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("provider", "purchase_token", name="uniq_provider_token"),
    )