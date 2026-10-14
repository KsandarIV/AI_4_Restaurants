import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from backend.database.connection import Base

class RestaurantTable(Base):
    __tablename__ = "tables"

    id = Column(Integer, primary_key=True, index=True)
    table_number = Column(Integer, unique=True, nullable=False)
    capacity = Column(Integer, nullable=False)
    location = Column(String(50), default="interno")  # interno, terrazza, giardino
    is_active = Column(Boolean, default=True)

    reservations = relationship("Reservation", back_populates="table")

    def __repr__(self):
        return f"<Table #{self.table_number} (cap={self.capacity}, loc={self.location})>"

class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    booking_code = Column(String(20), unique=True, index=True, nullable=False)
    customer_id = Column(String(100), index=True, nullable=False)  # Anonymized customer token
    table_id = Column(Integer, ForeignKey("tables.id"), nullable=True)
    date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    time = Column(String(5), nullable=False)  # HH:MM
    shift = Column(String(20), nullable=False)  # "pranzo" or "cena"
    guests_count = Column(Integer, nullable=False)
    status = Column(String(20), default="CONFIRMED")  # "CONFIRMED", "CANCELLED"
    special_requests = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), onupdate=lambda: datetime.datetime.now(datetime.timezone.utc))

    table = relationship("RestaurantTable", back_populates="reservations")

    def __repr__(self):
        return f"<Reservation {self.booking_code} on {self.date} {self.time} for {self.guests_count}p ({self.status})>"

class Customer(Base):
    """Contact data of a customer. This is the ONLY place where name and phone are stored.

    Reservations point to it through the anonymous `customer_id` token (no foreign key on purpose:
    it would need a migration of the existing SQLite file). Never expose name/phone to the LLM.
    """
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(String(100), unique=True, index=True, nullable=False)  # anonymous token, e.g. cust_8f3a1c9d2b4e
    name = Column(String(120), nullable=False)
    phone = Column(String(20), nullable=False)  # E.164, e.g. +393331234567
    consent_at = Column(DateTime, nullable=False)  # when the customer agreed to the use of the data
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc))

    def __repr__(self):
        return f"<Customer {self.customer_id}>"  # never print name/phone

class MenuItem(Base):
    __tablename__ = "menu_items"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(50), nullable=False, index=True)  # Antipasti, Primi, Secondi, Contorni, Dessert, Bevande
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=False)
    allergens = Column(String(255), default="")  # comma separated
    is_vegetarian = Column(Boolean, default=False)
    is_vegan = Column(Boolean, default=False)
    is_gluten_free = Column(Boolean, default=False)

    def __repr__(self):
        return f"<MenuItem {self.name} - €{self.price:.2f}>"

class RestaurantInfo(Base):
    __tablename__ = "restaurant_info"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(50), unique=True, index=True, nullable=False)
    value = Column(Text, nullable=False)
    description = Column(String(255), nullable=True)

    def __repr__(self):
        return f"<RestaurantInfo {self.key}>"
