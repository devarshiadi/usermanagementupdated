from sqlalchemy import Column, Integer, String, Boolean, Date, Float, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False)
    details = relationship("UserDetails", back_populates="user", uselist=False)

class UserDetails(Base):
    __tablename__ = "user_details"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    first_name = Column(String)
    last_name = Column(String)
    email = Column(String)
    mobile = Column(String)
    dob = Column(Date)
    gender = Column(String)
    current_semester = Column(String)
    tenth_percentage = Column(Float)
    twelfth_percentage = Column(Float)
    current_aggregate_percentage = Column(Float, nullable=True) # New field
    graduation_percentage = Column(Float)
    specialization = Column(String)
    placement_status = Column(String, nullable=True)
    company_name = Column(String, nullable=True)
    user = relationship("User", back_populates="details")
