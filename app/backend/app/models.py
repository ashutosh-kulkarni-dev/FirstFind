import datetime as dt

from sqlalchemy import (Column, DateTime, Float, ForeignKey, Integer, String,
                        Text, UniqueConstraint)
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(120), nullable=False)
    # Nullable so OAuth-only accounts (auth_provider != "local") can exist without
    # a password. verify_password already returns False for a missing/blank hash.
    password_hash = Column(String(255), nullable=True)
    auth_provider = Column(String(20), default="local", nullable=False)  # "local" | "google"
    google_sub = Column(String(64), unique=True, nullable=True, index=True)
    avatar_url = Column(String(300), nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    reviews = relationship("Review", back_populates="user")
    interactions = relationship("Interaction", back_populates="user")


class Store(Base):
    __tablename__ = "stores"
    id = Column(String(20), primary_key=True)  # blr-0001
    name = Column(String(200), nullable=False)
    area = Column(String(100), nullable=False)
    city = Column(String(80), default="Bengaluru")
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    open_time = Column(String(10), nullable=True)
    close_time = Column(String(10), nullable=True)
    timing_note = Column(String(200), nullable=True)
    notes = Column(String(500), nullable=True)
    phone = Column(String(30), nullable=True)
    instagram = Column(String(120), nullable=True)
    categories = Column(String(300), default="")       # comma-separated
    closed_days = Column(String(120), default="")      # comma-separated day names
    price_min = Column(Integer, nullable=True)
    price_max = Column(Integer, nullable=True)
    # Raw locality string from the source dataset ("Tavrekere Road, SG Palya"),
    # kept verbatim so Tier-2 token search can match sub-locality phrases.
    locality_raw = Column(String(200), nullable=True)
    # "locality" = Nominatim pin; "centroid" = backfilled from area centroid.
    # Tier-3 spatial ranking only trusts locality-precision pins.
    geocode_precision = Column(String(20), nullable=True)
    # Cached from Google Places API so subsequent runs skip the Find Place call.
    google_place_id = Column(String(120), nullable=True)
    # ML-derived
    experience_score = Column(Float, nullable=True)   # 0-5 blended score
    review_count = Column(Integer, default=0)
    zone_id = Column(Integer, nullable=True, index=True)

    reviews = relationship("Review", back_populates="store")


class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True)
    store_id = Column(String(20), ForeignKey("stores.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    rating = Column(Integer, nullable=False)  # 1-5
    text = Column(Text, default="")
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    # Source tracking for external reviews (Google Maps, future providers).
    source = Column(String(20), default="app")          # "app" | "google"
    external_id = Column(String(128), nullable=True)    # provider review id / stable hash
    # ML-derived
    sentiment = Column(String(20), nullable=True)        # positive/neutral/negative
    sentiment_score = Column(Float, nullable=True)   # compound in [-1, 1]
    store = relationship("Store", back_populates="reviews")
    user = relationship("User", back_populates="reviews")

    __table_args__ = (
        UniqueConstraint("store_id", "source", "external_id",
                         name="uq_review_source_external"),
    )


class Interaction(Base):
    __tablename__ = "interactions"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    store_id = Column(String(20), ForeignKey("stores.id"), nullable=False, index=True)
    kind = Column(String(20), nullable=False)  # view / save / like
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    user = relationship("User", back_populates="interactions")


class Zone(Base):
    __tablename__ = "zones"
    id = Column(Integer, primary_key=True)
    label = Column(String(120), nullable=False)      # geographic name (dominant area / locality_raw)
    center_lat = Column(Float)
    center_lng = Column(Float)
    radius_km = Column(Float)                        # 90th-pct haversine from centroid to members
    store_count = Column(Integer)
    avg_score = Column(Float)
    avg_price = Column(Float)                        # displayed fact only — never a filter
    description = Column(Text, default="")


class SavedList(Base):
    __tablename__ = "saved_lists"
    id           = Column(Integer, primary_key=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name         = Column(String(120), nullable=False)
    # Cluster provenance — lets the frontend re-open the list on the zones map.
    center_lat   = Column(Float, nullable=True)
    center_lng   = Column(Float, nullable=True)
    radius_km    = Column(Float, nullable=True)
    source_label = Column(String(160), nullable=True)   # cluster label at save time
    created_at   = Column(DateTime, default=dt.datetime.utcnow)
    items        = relationship("SavedListItem", back_populates="saved_list",
                                order_by="SavedListItem.position",
                                cascade="all, delete-orphan")


class SavedListItem(Base):
    __tablename__ = "saved_list_items"
    id        = Column(Integer, primary_key=True)
    list_id   = Column(Integer, ForeignKey("saved_lists.id"), nullable=False, index=True)
    store_id  = Column(String(20), ForeignKey("stores.id"), nullable=False)
    position  = Column(Integer, default=0)
    saved_list = relationship("SavedList", back_populates="items")


class Conversation(Base):
    __tablename__ = "conversations"
    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # session_id links a guest UUID to this record at claim time.
    session_id = Column(String(64), nullable=True, index=True)
    title      = Column(String(160), default="")   # first user message, truncated
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    updated_at = Column(DateTime, default=dt.datetime.utcnow)
    messages   = relationship("ChatMessage", back_populates="conversation",
                              order_by="ChatMessage.id",
                              cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id              = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"),
                             nullable=False, index=True)
    role            = Column(String(12), nullable=False)   # "user" | "assistant"
    text            = Column(Text, nullable=False)
    # Serialised assistant payload (stores/intent/suggestions) so a reopened
    # conversation can re-render cards, not just the text bubble.
    meta            = Column(Text, nullable=True)          # JSON or NULL
    created_at      = Column(DateTime, default=dt.datetime.utcnow)
    conversation    = relationship("Conversation", back_populates="messages")


class StoreSimilarity(Base):
    """Precomputed "similar stores" list, written by the recommender refit.

    Serving reads this table instead of the in-memory similarity matrix so every
    API worker returns identical results and recs survive a restart (the matrix
    is process-local; this table is the shared source of truth).
    """
    __tablename__ = "store_similarity"
    id = Column(Integer, primary_key=True)
    store_id = Column(String(20), ForeignKey("stores.id"), nullable=False, index=True)
    similar_id = Column(String(20), ForeignKey("stores.id"), nullable=False)
    rank = Column(Integer, nullable=False)   # 0 = most similar
    score = Column(Float, nullable=True)


class UserRecommendation(Base):
    """Precomputed per-user recommendations, written by the recommender refit.
    Same rationale as StoreSimilarity: read-from-DB keeps serving stateless."""
    __tablename__ = "user_recommendations"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    store_id = Column(String(20), ForeignKey("stores.id"), nullable=False)
    rank = Column(Integer, nullable=False)   # 0 = top pick
    score = Column(Float, nullable=True)
