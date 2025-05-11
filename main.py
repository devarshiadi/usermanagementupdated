from fastapi import FastAPI, Request, Form, Depends, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from database import engine, Base, SessionLocal
from models import User, UserDetails
from auth import authenticate_user, create_user, get_password_hash
import uvicorn
from datetime import datetime

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="your-secret-key")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/user/form", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "success": request.session.pop("success", None), "error": request.session.pop("error", None)})

@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "success": request.session.pop("success", None), "error": request.session.pop("error", None)})

@app.post("/login", response_class=HTMLResponse)
def login_post(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = authenticate_user(db, username, password)
    if user:
        request.session["user_id"] = user.id
        request.session["is_admin"] = user.is_admin
        request.session["success"] = "Login successful!"
        if user.is_admin:
            return RedirectResponse("/admin/dashboard", status_code=302)
        else:
            return RedirectResponse("/user/form", status_code=302)
    request.session["error"] = "Invalid credentials"
    return RedirectResponse("/login", status_code=302)

@app.get("/signup", response_class=HTMLResponse)
def signup_get(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request, "success": request.session.pop("success", None), "error": request.session.pop("error", None)})

@app.post("/signup", response_class=HTMLResponse)
def signup_post(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == username).first():
        request.session["error"] = "Username already exists"
        return RedirectResponse("/signup", status_code=302)
    create_user(db, username, password)
    request.session["success"] = "Signup successful! Please login."
    return RedirectResponse("/login", status_code=302)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

@app.get("/user/form", response_class=HTMLResponse)
def user_form_get(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=302)
    user = db.query(User).filter(User.id == user_id).first()
    details = user.details if user and user.details else None
    semester_options = [f"{i}{s} Semester" for i, s in [(1, 'st'), (2, 'nd'), (3, 'rd')] + [(j, 'th') for j in range(4,9)]] + ["Graduated"]
    specialization_options = ["BCA", "MCA", "B.Tech in Computer Science", "B.Tech in AI/ML"]
    return templates.TemplateResponse("user_form.html", {
        "request": request, 
        "details": details or {}, 
        "semester_options": semester_options,
        "specialization_options": specialization_options,
        "success": request.session.pop("success", None), 
        "error": request.session.pop("error", None)
    })

@app.post("/user/form", response_class=HTMLResponse)
def user_form_post(request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    mobile: str = Form(...),
    dob: str = Form(...),
    gender: str = Form(...),
    current_semester: str = Form(...),
    tenth_percentage: float = Form(...),
    twelfth_percentage: float = Form(...),
    current_aggregate_percentage: float = Form(None), # New
    graduation_percentage: float = Form(None), # Make nullable if not always provided
    specialization: str = Form(...),
    # experience_status: str = Form(...), # Removed
    placement_status: str = Form(None), 
    company_name: str = Form(None), 
    db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=302)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse("/login", status_code=302)

    if not (mobile and mobile.isdigit() and len(mobile) == 10):
        request.session["error"] = "Mobile number must be 10 digits."
        # Redirect back to the form, preserving other data is complex with current setup
        # For now, just show error and redirect. User might need to re-enter.
        return RedirectResponse("/user/form", status_code=302)

    details = user.details
    if not details:
        details = UserDetails(user_id=user.id)
        db.add(details)
        msg = "Details created!"
    else:
        msg = "Details updated!"
    details.first_name = first_name
    details.last_name = last_name
    details.email = email
    details.mobile = mobile
    details.dob = datetime.strptime(dob, "%Y-%m-%d").date()
    details.gender = gender
    details.current_semester = current_semester
    details.tenth_percentage = tenth_percentage
    details.twelfth_percentage = twelfth_percentage
    details.specialization = specialization

    # Conditional logic for percentages and placement
    if current_semester == "Graduated":
        details.graduation_percentage = graduation_percentage
        details.placement_status = placement_status
        details.company_name = company_name if placement_status == "Placed" else None
        details.current_aggregate_percentage = None # Nullify if graduated
    else: # Semesters 1-8
        details.current_aggregate_percentage = current_aggregate_percentage
        details.graduation_percentage = None # Nullify if not graduated
        details.placement_status = None
        details.company_name = None
        
    db.commit()
    request.session["success"] = msg
    return RedirectResponse("/user/form", status_code=302)

@app.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request, 
                    search: str = "", 
                    graduation_status: str = None,
                    specialization_filter: str = None,
                    less_than_60_grad: bool = False,
                    less_than_60_current_agg: bool = False, # New filter
                    db: Session = Depends(get_db)):
    if not request.session.get("is_admin"):
        return RedirectResponse("/login", status_code=302)
    
    query = db.query(User).join(UserDetails, User.id == UserDetails.user_id).filter(User.is_admin == False)

    if search:
        query = query.filter(
            (User.username.contains(search)) |
            (UserDetails.first_name.contains(search)) |
            (UserDetails.last_name.contains(search)) |
            (UserDetails.email.contains(search))
        )
    
    if graduation_status:
        if graduation_status == "Graduated":
            # Assuming "Graduated" is a value in current_semester or a similar field
            query = query.filter(UserDetails.current_semester == "Graduated")
        elif graduation_status == "Pursuing":
            query = query.filter(UserDetails.current_semester != "Graduated") # Or specific values like "1st", "2nd" etc.
            # This might need refinement based on exact values stored for "pursuing"

    if specialization_filter:
        query = query.filter(UserDetails.specialization.contains(specialization_filter))

    if less_than_60_grad: # For graduated students
        query = query.filter(UserDetails.current_semester == "Graduated", UserDetails.graduation_percentage < 60.0)
    
    if less_than_60_current_agg: # For pursuing students
        query = query.filter(UserDetails.current_semester != "Graduated", UserDetails.current_aggregate_percentage < 60.0)
        
    users = query.all()

    # For summary cards - this is a simplified version.
    # More complex aggregations might require separate queries or more advanced SQLAlchemy.
    total_users = db.query(User).filter(User.is_admin == False).count()
    graduated_count = db.query(UserDetails).join(User).filter(User.is_admin == False, UserDetails.current_semester == "Graduated").count()
    # Pursuing count: any non-admin user whose current_semester is not "Graduated"
    pursuing_count = db.query(UserDetails).join(User).filter(User.is_admin == False, UserDetails.current_semester != "Graduated").count()
    # Count for graduated students < 60%
    less_than_60_grad_count = db.query(UserDetails).join(User).filter(User.is_admin == False, UserDetails.current_semester == "Graduated", UserDetails.graduation_percentage < 60.0).count()
    # Count for pursuing students < 60% current aggregate
    less_than_60_current_agg_count = db.query(UserDetails).join(User).filter(User.is_admin == False, UserDetails.current_semester != "Graduated", UserDetails.current_aggregate_percentage < 60.0).count()
    # Placed count for non-admin users
    placed_count = db.query(UserDetails).join(User).filter(User.is_admin == False, UserDetails.placement_status == "Placed").count()

    specialization_options_for_filter = ["BCA", "MCA", "B.Tech in Computer Science", "B.Tech in AI/ML"] # Duplicated for now, consider centralizing

    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request, 
        "users": users, 
        "search": search,
        "graduation_status": graduation_status,
        "specialization_filter": specialization_filter,
        "less_than_60_grad": less_than_60_grad, # For graduated
        "less_than_60_current_agg": less_than_60_current_agg, # For pursuing
        "total_users": total_users,
        "graduated_count": graduated_count,
        "pursuing_count": pursuing_count,
        "less_than_60_grad_count": less_than_60_grad_count,
        "less_than_60_current_agg_count": less_than_60_current_agg_count,
        "placed_count": placed_count,
        "specialization_options": specialization_options_for_filter, 
        "success": request.session.pop("success", None), 
        "error": request.session.pop("error", None)
    })

@app.get("/admin/user/{user_id}", response_class=HTMLResponse)
def admin_view_user(request: Request, user_id: int, db: Session = Depends(get_db)):
    if not request.session.get("is_admin"):
        return RedirectResponse("/login", status_code=302)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse("/admin/dashboard", status_code=302)
    details = user.details
    academic_remarks = []
    if details and details.current_semester != "Graduated":
        if details.twelfth_percentage is not None and details.tenth_percentage is not None:
            if details.twelfth_percentage > details.tenth_percentage:
                academic_remarks.append(f"Improved from 10th ({details.tenth_percentage}%) to 12th ({details.twelfth_percentage}%).")
            elif details.twelfth_percentage < details.tenth_percentage:
                academic_remarks.append(f"Declined from 10th ({details.tenth_percentage}%) to 12th ({details.twelfth_percentage}%).")
            else:
                academic_remarks.append(f"Maintained performance from 10th to 12th ({details.tenth_percentage}%).")
        
        if details.current_aggregate_percentage is not None and details.twelfth_percentage is not None:
            if details.current_aggregate_percentage > details.twelfth_percentage:
                academic_remarks.append(f"Improved from 12th ({details.twelfth_percentage}%) to Current Aggregate ({details.current_aggregate_percentage}%).")
            elif details.current_aggregate_percentage < details.twelfth_percentage:
                academic_remarks.append(f"Declined from 12th ({details.twelfth_percentage}%) to Current Aggregate ({details.current_aggregate_percentage}%).")
            else:
                academic_remarks.append(f"Maintained performance from 12th to Current Aggregate ({details.current_aggregate_percentage}%).")
    elif details and details.current_semester == "Graduated":
        if details.graduation_percentage is not None and details.twelfth_percentage is not None:
             if details.graduation_percentage > details.twelfth_percentage:
                academic_remarks.append(f"Improved from 12th ({details.twelfth_percentage}%) to Graduation ({details.graduation_percentage}%).")
             elif details.graduation_percentage < details.twelfth_percentage:
                academic_remarks.append(f"Declined from 12th ({details.twelfth_percentage}%) to Graduation ({details.graduation_percentage}%).")
             else:
                academic_remarks.append(f"Maintained performance from 12th to Graduation ({details.graduation_percentage}%).")


    return templates.TemplateResponse("admin_view.html", {
        "request": request, 
        "user": user, 
        "details": details,
        "academic_remarks": academic_remarks # Pass remarks to template
    })

@app.get("/admin/user/{user_id}/edit", response_class=HTMLResponse)
def admin_edit_user_get(request: Request, user_id: int, db: Session = Depends(get_db)):
    if not request.session.get("is_admin"):
        return RedirectResponse("/login", status_code=302)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse("/admin/dashboard", status_code=302)
    details = user.details or None
    semester_options = [f"{i}{s} Semester" for i, s in [(1, 'st'), (2, 'nd'), (3, 'rd')] + [(j, 'th') for j in range(4,9)]] + ["Graduated"]
    specialization_options = ["BCA", "MCA", "B.Tech in Computer Science", "B.Tech in AI/ML"]
    return templates.TemplateResponse("admin_edit.html", {
        "request": request, 
        "user": user, 
        "details": details or {}, 
        "semester_options": semester_options,
        "specialization_options": specialization_options,
        "success": request.session.pop("success", None), 
        "error": request.session.pop("error", None)
    })

@app.post("/admin/user/{user_id}/edit", response_class=HTMLResponse)
def admin_edit_user_post(request: Request, user_id: int,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    mobile: str = Form(...),
    dob: str = Form(...),
    gender: str = Form(...),
    current_semester: str = Form(...),
    tenth_percentage: float = Form(...),
    twelfth_percentage: float = Form(...),
    current_aggregate_percentage: float = Form(None), # New
    graduation_percentage: float = Form(None), # Make nullable
    specialization: str = Form(...),
    # experience_status: str = Form(...), # Removed
    placement_status: str = Form(None),
    company_name: str = Form(None),
    db: Session = Depends(get_db)):
    if not request.session.get("is_admin"):
        return RedirectResponse("/login", status_code=302)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse("/admin/dashboard", status_code=302)

    if not (mobile and mobile.isdigit() and len(mobile) == 10):
        request.session["error"] = "Mobile number must be 10 digits."
        # Redirect back to the edit form
        return RedirectResponse(f"/admin/user/{user_id}/edit", status_code=302)

    details = user.details
    if not details:
        details = UserDetails(user_id=user.id)
        db.add(details)
        msg = "User details created!"
    else:
        msg = "User details updated!"
    details.first_name = first_name
    details.last_name = last_name
    details.email = email
    details.mobile = mobile
    details.dob = datetime.strptime(dob, "%Y-%m-%d").date()
    details.gender = gender
    details.current_semester = current_semester
    details.tenth_percentage = tenth_percentage
    details.twelfth_percentage = twelfth_percentage
    details.specialization = specialization

    # Conditional logic for percentages and placement
    if current_semester == "Graduated":
        details.graduation_percentage = graduation_percentage
        details.placement_status = placement_status
        details.company_name = company_name if placement_status == "Placed" else None
        details.current_aggregate_percentage = None # Nullify if graduated
    else: # Semesters 1-8
        details.current_aggregate_percentage = current_aggregate_percentage
        details.graduation_percentage = None # Nullify if not graduated
        details.placement_status = None
        details.company_name = None

    db.commit()
    request.session["success"] = msg
    return RedirectResponse(f"/admin/user/{user_id}/edit", status_code=302)

@app.get("/admin/user/{user_id}/delete")
def admin_delete_user(request: Request, user_id: int, db: Session = Depends(get_db)):
    if not request.session.get("is_admin"):
        return RedirectResponse("/login", status_code=302)
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        db.delete(user)
        db.commit()
        request.session["success"] = "User deleted!"
    return RedirectResponse("/admin/dashboard", status_code=302)

@app.get("/create-admin")
def create_admin(request: Request, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == "admin@149gmail.com").first():
        request.session["error"] = "Admin already exists."
        return RedirectResponse("/login", status_code=302)
    create_user(db, "admin@149gmail.com", "Admin@149", is_admin=True)
    request.session["success"] = "Admin created. You can now login as admin."
    return RedirectResponse("/login", status_code=302)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=7860, reload=True)
