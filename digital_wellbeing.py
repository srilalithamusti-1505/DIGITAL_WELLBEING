import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import sqlite3
from datetime import datetime, timedelta
from tkinter import ttk
from collections import Counter
import matplotlib.pyplot as plt
from matplotlib import rcParams
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import os
import pyotp 

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OTP_SECRET_FILE = os.path.join(BASE_DIR, "admin_otp_secret.txt")

def load_or_create_otp_secret():
    if os.path.exists(OTP_SECRET_FILE):
        with open(OTP_SECRET_FILE) as f:
            return f.read().strip(), False
    secret = pyotp.random_base32()
    with open(OTP_SECRET_FILE, "w") as f:
        f.write(secret)
    return secret, True

OTP_SECRET, OTP_IS_NEW = load_or_create_otp_secret()
totp = pyotp.TOTP(OTP_SECRET)
failed_otp_attempts = 0

# ------------------- DATABASE SETUP -------------------
db_path = os.path.join(BASE_DIR, "digital_wellbeing.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS mood_tracker (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    mood TEXT NOT NULL,
    feeling TEXT,
    date_time TEXT NOT NULL,
    day TEXT NOT NULL
)
""")
conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL
)
""")
conn.commit()

cursor.execute("""
CREATE TABLE IF NOT EXISTS diary_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    content TEXT NOT NULL,
    date_time TEXT NOT NULL
)
""")
conn.commit()
current_user = None  # global variable to store logged-in user

# ---------------- Functions ----------------
def login_user():
    global current_user
    username = username_entry.get().strip()
    password = password_entry.get().strip()

    if not username or not password:
        messagebox.showerror("Error", "Please enter username and password!")
        return

    cursor.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
    user = cursor.fetchone()

    if user:
        current_user = username
        show_frame("DASHBOARD FRAME")
        create_menu_button()  # show menu
    else:
        messagebox.showerror("Login Failed", "Incorrect username or password!")

menu_button = None  # global variable to store menu button

def create_menu_button():
    global menu_button
    if menu_button is None:
        menu_button = tk.Button(
            dashboard_frame,  # <- parent is dashboard_frame
            image=menu_photo,
            bg="#DCDCDC", fg = "#333333",
            borderwidth=0,
            command=lambda: menu.post(
                menu_button.winfo_rootx(),
                menu_button.winfo_rooty() + menu_button.winfo_height()
            )
        )
        menu_button.place(x=10, y=10)  # top-left corner
    menu_button.lift()

def show_frame(page):
    frame = frames[page]
    frame.tkraise()
    if page == "ADMIN FRAME":
        admin_dashboard_frame.place_forget()
        admin_login_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        admin_login_frame.tkraise()
        adminusername_entry.delete(0, tk.END)
        adminpassword_entry.delete(0, tk.END)
        message_label.config(text="")
    
    # Hide menu button on login/signup
    if page in ["LOGIN FRAME", "CREATE ACCOUNT FRAME"]:
        if menu_button:
            menu_button.place_forget()
    else:
        if menu_button:
            menu_button.place(x=10, y=10)
    if menu_button:  # check if it exists
        menu_button.lift()

    if page == "DASHBOARD FRAME":
        load_dashboard_frame()    # update last 5 moods and all messages
    elif page == "STATISTICS FRAME":
        update_mood_counts_buttons()  # refresh buttons whenever statistics frame is shown

def save_mood(mood):
    """Save mood along with username, feeling, date, and day"""
    if not current_user:
        messagebox.showerror("Error", "No user is logged in!")
        return
    
    feeling = feeling_text.get("1.0", tk.END).strip()
    
    now = datetime.now()
    date_time = now.strftime("%Y-%m-%d %H:%M:%S")
    day = now.strftime("%A")
    
    cursor.execute("""
        INSERT INTO mood_tracker (username, mood, feeling, date_time, day)
        VALUES (?, ?, ?, ?, ?)
    """, (current_user, mood, feeling, date_time, day))
    
    conn.commit()
    messagebox.showinfo("Saved", f"Mood saved: {mood} at {date_time}")
    feeling_text.delete("1.0", tk.END)

    update_mood_counts_buttons() # Update dynamically  # refresh buttons after adding mood

def submit_feeling():
    """Save the feeling text into the database"""
    if not current_user:
        messagebox.showerror("Error", "No user is logged in!")
        return
    
    feeling = feeling_text.get("1.0", tk.END).strip()
    if not feeling:
        messagebox.showerror("Error", "Please write something first!")
        return

    now = datetime.now()
    date_time = now.strftime("%Y-%m-%d %H:%M:%S")
    day = now.strftime("%A")

    mood = "MESSAGES"  # default, or store last clicked mood in a variable

    cursor.execute("""
    INSERT INTO mood_tracker (username, mood, feeling, date_time, day)
    VALUES (?, ?, ?, ?, ?)
""", (current_user, mood, feeling, date_time, day))

    conn.commit()
    messagebox.showinfo("Saved", f"Feeling saved at {date_time}")

    feeling_text.delete("1.0", tk.END) # Clear text box

def create_account():
    username = reg_username_entry.get().strip()
    password = reg_password_entry.get().strip()
    confirm = reg_confirm_entry.get().strip()

    if not username or not password:
        messagebox.showerror("Error", "Username and password required!")
        return
    if password != confirm:
        messagebox.showerror("Error", "Passwords do not match!")
        return

    try:
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
        conn.commit()
        messagebox.showinfo("Success", "Account created successfully!")
        
        show_frame("LOGIN FRAME") # Go back to login
    except sqlite3.IntegrityError:
        messagebox.showerror("Error", "Username already exists!")

current_graph_canvas = None  # Global variable to store current graph canvas
no_data_label = None         # Global variable to store the "no data" message

def update_mood_counts_buttons():
    """Display mood counts as buttons, wrapped in rows below (or above) the graph"""
    # Clear previous buttons
    for widget in mood_count_frame.winfo_children():
        widget.destroy()

    if not current_user:
        return

    # Fetch all moods for the current user
    cursor.execute("SELECT mood FROM mood_tracker WHERE username=?", (current_user,))
    data = [row[0] for row in cursor.fetchall() if row[0] not in ("Neutral", "MESSAGES")]

    mood_counts = Counter(data)     # Count moods

    # Create buttons, wrap automatically
    max_per_row = 5
    row = 0
    col = 0
    for mood, count in mood_counts.items():
        btn = tk.Button(mood_count_frame, text=f"{mood}: {count}", 
                        bg="#FCE4EC", fg = "#333333", font=("Arial", 12), relief="raised")
        btn.grid(row=row, column=col, padx=5, pady=5, sticky="w")
        col += 1
        if col >= max_per_row:
            col = 0
            row += 1

def plot_mood_graph(period):
    global current_graph_canvas, no_data_label

    # 1️⃣ Clear previous graph and message FIRST
    if current_graph_canvas:
        current_graph_canvas.get_tk_widget().destroy()
        current_graph_canvas = None
    if no_data_label:
        no_data_label.destroy()
        no_data_label = None
    plt.close("all")  # free up old matplotlib figures

    # 2️⃣ Fetch data
    days = time_options[period]
    if days is not None:
        cutoff = datetime.now() - timedelta(days=days)
        cursor.execute("""
            SELECT mood FROM mood_tracker
            WHERE username=? AND date_time>=? AND mood GLOB '*[^a-zA-Z0-9 ]*'
            """,
            (current_user, cutoff.strftime("%Y-%m-%d %H:%M:%S")))
    else:
        cursor.execute("""
            SELECT mood FROM mood_tracker
            WHERE username=? AND mood GLOB '*[^a-zA-Z0-9 ]*'
            """, (current_user,))
    data = [row[0] for row in cursor.fetchall()]

    # 3️⃣ No data: show ONE message (replaces the old one)
    if not data:
        no_data_label = tk.Label(scroll_statistics, text="No mood entries for this period.",
                                 bg="#FCE4EC", fg="#333333", font=("Arial", 12))
        no_data_label.pack(pady=10)
        update_mood_counts_buttons()
        return

    mood_counts = Counter(data)

    label_map = {
        "Happy 😃": "Happy", "Excited 🤩": "Excited", "High Energy 😄": "High Energy",
        "Calm 😌": "Calm", "Low 😔": "Low", "Angry 😡": "Angry", "Tired 😴": "Tired",
        "Anxious 😟": "Anxious", "Confused 😕": "Confused", "Surprised 😲": "Surprised",
        "Lonely 😞": "Lonely", "Grateful 🙏": "Grateful", "Motivated 💪": "Motivated",
        "Playful 😜": "Playful", "Bored 😐": "Bored"
    }

    # 4️⃣ Plot graph
    fig, ax = plt.subplots(figsize=(5, 3))
    ax.bar([label_map.get(m, m) for m in mood_counts.keys()],
           mood_counts.values(), color="#FF4081")
    ax.set_title("Mood Tracker")
    ax.set_xlabel("Moods")
    ax.set_ylabel("Count")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()

    # 5️⃣ Embed in Tkinter
    current_graph_canvas = FigureCanvasTkAgg(fig, master=scroll_statistics)
    current_graph_canvas.draw()
    current_graph_canvas.get_tk_widget().pack()
    update_mood_counts_buttons()

def update_datetime():
    now = datetime.now()
    date_str = now.strftime("%A, %d %B %Y")  # Day, Date Month Year
    time_str = now.strftime("%H:%M:%S")      # Hour:Minute:Second
    date_time_label.config(text=f"{date_str} | {time_str}")
    # Update every 1 second
    date_time_label.after(1000, update_datetime)

def update_mood_counts():
    if not current_user:
        return

    # Fetch all moods for the current user
    cursor.execute("SELECT mood FROM mood_tracker WHERE username=?", (current_user,))
    data = [row[0] for row in cursor.fetchall()]

    # Clear previous horizontal count labels
    for widget in mood_count_frame.winfo_children():
        widget.destroy()

    if not data:
        tk.Label(mood_count_frame, text="No mood entries yet.", bg="#FCE4EC", fg = "#333333", font=("Arial", 16)).pack()
        return

    mood_counts = Counter(data)

    # Display counts horizontally
    for mood, count in mood_counts.items():
        label = tk.Label(mood_count_frame, text=f"{mood}: {count}",
                         bg="#FCE4EC", fg = "#333333", font=("Arial", 14))
        label.pack(side="left", padx=10)

def make_scrollable_frame(container):
    # Frame to hold canvas + scrollbar
    wrapper = tk.Frame(container, bg=container["bg"])
    wrapper.pack(fill="both", expand=True)

    # Create canvas
    canvas = tk.Canvas(wrapper, borderwidth=0, highlightthickness=0, bg=container["bg"])
    canvas.pack(side="left", fill="both", expand=True)

    # Create scrollbar
    scrollbar = tk.Scrollbar(wrapper, orient="vertical", command=canvas.yview)
    scrollbar.pack(side="right", fill="y")
    canvas.configure(yscrollcommand=scrollbar.set)

    # Scrollable frame inside canvas
    scrollable_frame = tk.Frame(canvas, bg=container["bg"])
    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

    return scrollable_frame, canvas

def login_admin():
    global failed_otp_attempts
    username = adminusername_entry.get().strip()
    code = adminpassword_entry.get().strip()

    if failed_otp_attempts >= 5:
        message_label.config(text="Too many attempts. Restart the app.", fg="red")
    elif username != "admin":
        message_label.config(text="Only admin has entry!", fg="red")
    elif not totp.verify(code, valid_window=1):
        failed_otp_attempts += 1
        message_label.config(text="Invalid or expired code!", fg="red")
    else:
        failed_otp_attempts = 0
        message_label.config(text="Login Successful!", fg="green")
        open_admin_frame()

def view_diary(entry_text):
    """Popup to show diary or message content"""
    win = tk.Toplevel(admin_dashboard_frame)
    win.title("Diary Entry")
    win.geometry("500x400")

    text_widget = tk.Text(win, wrap="word")
    text_widget.pack(fill="both", expand=True)
    text_widget.insert("1.0", entry_text)
    text_widget.config(state="disabled")

def view_message(entry_text):
    """Popup to show diary or message content"""
    win = tk.Toplevel(admin_dashboard_frame)
    win.title("Message")
    win.geometry("500x400")

    text_widget = tk.Text(win, wrap="word")
    text_widget.pack(fill="both", expand=True)
    text_widget.insert("1.0", entry_text)
    text_widget.config(state="disabled")

def load_activity_table():
    # Clear previous entries
    activity_table.delete(*activity_table.get_children())
    
    # Fetch mood/message entries
    cursor.execute("""
        SELECT date_time, username, mood AS mood, feeling AS message, NULL AS diary
        FROM mood_tracker
    """)
    mood_rows = cursor.fetchall()
    
    # Fetch diary entries
    cursor.execute("""
        SELECT date_time, username, '' AS mood, '' AS message, content AS diary
        FROM diary_entries
    """)
    diary_rows = cursor.fetchall()

    # Combine and sort by date_time descending
    all_rows = mood_rows + diary_rows
    all_rows.sort(key=lambda x: x[0], reverse=True)  # sort by date_time descending

    for dt, user, mood, message, diary in all_rows:
        display_message = "View Message" if message else ""
        display_diary = "View Diary" if diary else ""
        activity_table.insert("", "end", values=(dt, user, mood, display_message, display_diary))

    # Double-click binding
    def on_double_click(event):
        item_id = activity_table.identify_row(event.y)
        if not item_id:
            return
        values = activity_table.item(item_id, "values")
        
        # Check which column was clicked
        column = activity_table.identify_column(event.x)
        if column == "#4" and values[3]:  # Message column
            # Fetch message content from DB
            dt_clicked = values[0]
            username_clicked = values[1]
            cursor.execute("""
                SELECT feeling FROM mood_tracker
                WHERE username=? AND date_time=?
            """, (username_clicked, dt_clicked))
            content = cursor.fetchone()
            if content:
                view_message(content[0])
        elif column == "#5" and values[4]:  # Diary column
            # Fetch diary content from DB
            dt_clicked = values[0]
            username_clicked = values[1]
            cursor.execute("""
                SELECT content FROM diary_entries
                WHERE username=? AND date_time=?
            """, (username_clicked, dt_clicked))
            content = cursor.fetchone()
            if content:
                view_diary(content[0])

    activity_table.bind("<Double-1>", on_double_click)

def open_admin_frame():
    admin_login_frame.place_forget()  # hide login
    admin_dashboard_frame.place(relx=0, rely=0, relwidth=1, relheight=1)  # place it only now
    refresh_tables()

def load_users_table():
    users_table.delete(*users_table.get_children())
    cursor.execute("SELECT id, username, password FROM users")
    rows = cursor.fetchall()
    for row in rows:
        users_table.insert("", "end", values=row)

def refresh_tables():
    load_users_table()
    load_activity_table()

def save_diary_entry():
    if not current_user:
        messagebox.showerror("Error", "No user is logged in!")
        return

    content = diary_text.get("1.0", tk.END).strip()
    if not content:
        messagebox.showerror("Error", "Diary entry is empty!")
        return

    now = datetime.now()
    date_time = now.strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
        INSERT INTO diary_entries (username, content, date_time)
        VALUES (?, ?, ?)
    """, (current_user, content, date_time))
    conn.commit()

    messagebox.showinfo("Saved", f"Diary entry saved at {date_time}")
    diary_text.delete("1.0", tk.END)
    now = datetime.now()
    diary_text.insert("1.0", f"Date: {now.strftime('%Y-%m-%d')}\nDay: {now.strftime('%A')}\nTime: {now.strftime('%I:%M %p')}\n\nDear Diary,\n")

def view_all_diary_entries():
    if not current_user:
        messagebox.showerror("Error", "No user is logged in!")
        return

    # Create top-level window
    win = tk.Toplevel(root)
    win.title("All Diary Entries")
    win.geometry("700x500")
    win.configure(bg="#FFF5E4")

    # ---------------- Scrollable Frame Setup ----------------
    container = tk.Frame(win, bg="#FFF5E4")
    container.pack(fill="both", expand=True)

    canvas = tk.Canvas(container, bg="#FFF5E4", highlightthickness=0)
    scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
    scrollable_frame = tk.Frame(canvas, bg="#FFF5E4")

    # Update scrollregion whenever the frame changes
    def on_frame_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))
    
    scrollable_frame.bind("<Configure>", on_frame_configure)

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # ---------------- Fetch Diary Entries ----------------
    cursor.execute("""
        SELECT date_time, content FROM diary_entries
        WHERE username=?
        ORDER BY date_time DESC
    """, (current_user,))
    entries = cursor.fetchall()

    if not entries:
        tk.Label(scrollable_frame, text="No diary entries yet.", font=("Arial", 14),
                 bg="#FFF5E4", fg="#333333").pack(pady=10)
        return

    # ---------------- Display Entries ----------------
    for dt, content in entries:
        entry_text = f"{dt}:\n{content}\n{'-'*50}"
        tk.Label(scrollable_frame, text=entry_text, anchor="w", justify="left",
                 wraplength=650, bg="#FFFFFF", fg="#333333", font=("Arial", 12),
                 padx=10, pady=5).pack(fill="x", padx=10, pady=5)

def load_dashboard_frame():
    if current_user is None:
        return
    
    # ---------- Last 5 Non-Neutral Moods ----------
    for widget in dashboard_mood_button_frame.winfo_children():
        widget.destroy()
    
    cursor.execute("""
        SELECT mood FROM mood_tracker 
        WHERE username=? AND mood NOT IN ("Neutral", "MESSAGES")
        ORDER BY date_time DESC LIMIT 5
    """, (current_user,))
    last_moods = [row[0] for row in cursor.fetchall()]
    
    for mood in last_moods:
        btn = tk.Button(dashboard_mood_button_frame, text=mood, font=("Arial", 12), bg="#E0E0E0", fg = "#333333")
        btn.pack(side="left", padx=5, pady=5)

    # ---------- Last 5 Neutral Messages ----------
    for widget in neutral_message_inner_frame.winfo_children():
        if isinstance(widget, tk.Label) and getattr(widget, "is_data_label", False):
            widget.destroy()
    
    cursor.execute("""
        SELECT date_time, feeling FROM mood_tracker
        WHERE username=? AND mood IN ("Neutral", "MESSAGES")
        ORDER BY date_time DESC LIMIT 5
    """, (current_user,))
    messages = cursor.fetchall()
    
    for dt, feeling in messages:
        msg_text = f"{dt}: {feeling}"
        lbl = tk.Label(neutral_message_inner_frame, text=msg_text, anchor="w", justify="left",
                       wraplength=600, bg="#FFF5E4", fg = "#333333", font=("Arial", 12))
        lbl.is_data_label = True
        lbl.pack(fill="x", padx=5, pady=2)

    # ---------- Last 5 Diary Entries ----------
    for widget in diary_inner_frame.winfo_children():
        if isinstance(widget, tk.Label) and getattr(widget, "is_data_label", False):
            widget.destroy()
    
    cursor.execute("""
        SELECT date_time, content FROM diary_entries
        WHERE username=? 
        ORDER BY date_time DESC LIMIT 5
    """, (current_user,))
    diary_entries = cursor.fetchall()
    
    for dt, entry in diary_entries:
        entry_text = f"{dt}: {entry}"
        lbl = tk.Label(diary_inner_frame, text=entry_text, anchor="w", justify="left",
                       wraplength=600, bg="#FFF5E4", fg = "#333333", font=("Arial", 12))
        lbl.is_data_label = True
        lbl.pack(fill="x", padx=5, pady=2)

def show_dashboard():
    login_frame.place_forget()
    dashboard_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
    load_users_table()
    load_activity_table()

def logout():
    global current_user, current_graph_canvas, no_data_label
    current_user = None
    username_entry.delete(0, tk.END)
    password_entry.delete(0, tk.END)
    feeling_text.delete("1.0", tk.END)
    if current_graph_canvas:
        current_graph_canvas.get_tk_widget().destroy()
        current_graph_canvas = None
    if no_data_label:
        no_data_label.destroy()
        no_data_label = None
    admin_dashboard_frame.place_forget()
    show_frame("LOGIN FRAME")


# ---------------- Main Window ----------------
root = tk.Tk()
root.title("Digital Wellbeing Login")

# Set your desired window size
window_width = 1200
window_height = 900

# Get the screen width and height
screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()

# Calculate the position for centering
x = int((screen_width / 2) - (window_width / 2))
y = int((screen_height / 2) - (window_height / 2))

# Set the geometry with width, height, and position
root.geometry(f"{window_width}x{window_height}+{x}+{y}")
root.resizable(True, True)

# ---------------- Container for all frames ----------------
container = tk.Frame(root)
container.pack(fill="both", expand=True)
frames={}

# ---------------- LOGIN FRAME ----------------
# Login page container frame
login_frame = tk.Frame(container, bg="#FFF8E1")
login_frame.place(relwidth=1, relheight=1)

left_frame = tk.Frame(login_frame, width=400, height=400)
left_frame.place(relx=0, rely=0, relwidth=0.5, relheight=1)

# Load image For login page image VERSATILE IMAGE PATHS FOR ANY DEVICE
img_path = os.path.join(BASE_DIR, "PICS", "Login.jpeg")  # ✅ Include image filename and extension
img = Image.open(img_path)
img = img.resize((400, 400), Image.LANCZOS)
photo = ImageTk.PhotoImage(img)

img = img.resize((400,400), Image.LANCZOS)
photo = ImageTk.PhotoImage(img)

img_label = tk.Label(left_frame, image=photo, bg="#FFF8E1", fg = "#333333")
img_label.image = photo  # keep reference
img_label.place(relx=-0.25, rely=0, relwidth=1, relheight=1)  # ✅ fill the frame

right_frame = tk.Frame(login_frame, width=400, height=400, bg="#FFF8E1")
right_frame.place(relx=0.5, rely=0, relwidth=0.5, relheight=1)

tk.Label(right_frame, text="LOGIN", foreground = "#333333", bg = "#FFF8E1", font=("Arial", 24, "bold")).pack(pady=30)

label = tk.Label(right_frame, text="USERNAME", foreground = "#333333", bg = "#FFF8E1")  # Create label
label.pack()  # Display it

username_entry = tk.Entry(right_frame, font=("Arial", 14))
username_entry.pack(pady=10)
username_entry.insert(0, "")

label = tk.Label(right_frame, text="PASSWORD", foreground = "#333333", bg = "#FFF8E1")  # Create label
label.pack()  # Display it

password_entry = tk.Entry(right_frame, font=("Arial", 14), show="*")
password_entry.pack(pady=10)
password_entry.insert(0, "")

tk.Button(right_frame, text="LOGIN", font=("Arial", 14),
          bg="#4CAF50", foreground="#333333", activebackground="#45a049",
          activeforeground="#FFF8E1", relief="raised",
          command=login_user).place(x=250, y=300)

tk.Button(right_frame, text="CREATE ACCOUNT", font=("Arial", 14),
          bg="#2196F3", foreground="#333333",
          command=lambda: show_frame("CREATE ACCOUNT FRAME")).place(x=215, y=400)

frames["LEFT FRAME"] = left_frame

frames["LOGIN FRAME"] = login_frame

# ---------- CREATE ACCOUNT FRAME ----------
create_account_frame = tk.Frame(container, bg="#E1F5FE")
create_account_frame.place(relwidth=1, relheight=1)

tk.Label(create_account_frame, text="CREATE ACCOUNT", font=("Arial", 24, "bold"),
         foreground="#333333", bg="#E1F5FE").pack(pady=30)

tk.Label(create_account_frame, text="Username:", bg="#E1F5FE", fg = "#333333").pack()
reg_username_entry = tk.Entry(create_account_frame, font=("Arial", 14))
reg_username_entry.pack(pady=10)

tk.Label(create_account_frame, text="Password:", bg="#E1F5FE", fg = "#333333").pack()
reg_password_entry = tk.Entry(create_account_frame, font=("Arial", 14), show="*")
reg_password_entry.pack(pady=10)

tk.Label(create_account_frame, text="Confirm Password:", bg="#E1F5FE", fg = "#333333").pack()
reg_confirm_entry = tk.Entry(create_account_frame, font=("Arial", 14), show="*")
reg_confirm_entry.pack(pady=10)

tk.Button(create_account_frame, text="Submit",
          font=("Arial", 14, "bold"),
          bg="#4CAF50", foreground="#333333",
          command=create_account).pack(pady=20)

# ---- BACK BUTTON ----
def go_back_to_login():
    # Clear the fields so old input doesn't remain
    reg_username_entry.delete(0, tk.END)
    reg_password_entry.delete(0, tk.END)
    reg_confirm_entry.delete(0, tk.END)
    show_frame("LOGIN FRAME")

tk.Button(create_account_frame, text="← Back to Login",
          font=("Arial", 14),
          bg="#E0E0E0", foreground="#333333",
          command=go_back_to_login).pack(pady=5)

frames["CREATE ACCOUNT FRAME"] = create_account_frame

# ---------------- Diary Frame ----------------
diary_frame = tk.Frame(container, bg="#FFF5E4")
diary_frame.place(relwidth=1, relheight=1)

# Title
tk.Label(diary_frame, text="PERSONAL DIARY", font=("Arial", 16, "bold"), bg="#FFF5E4", fg = "#333333").pack(pady=5)
tk.Label(diary_frame, text="📝 MY DIARY", font=("Arial", 20, "bold"), bg="#FFF5E4", foreground="#333333").pack(pady=10)

# Text box to write new diary entry with scrollbar
diary_text_frame = tk.Frame(diary_frame, bg="#FFF5E4")
diary_text_frame.pack(fill="both", expand=False, padx=100, pady=100)

# Create the Text widget
diary_text = tk.Text(diary_text_frame, height=30, font=("Arial", 12), wrap="word")
diary_text.pack(side="left", fill="both", expand=True)

# Add vertical scrollbar
diary_scrollbar = tk.Scrollbar(diary_text_frame, orient="vertical", command=diary_text.yview)
diary_scrollbar.pack(side="right", fill="y")

# Configure Text widget to work with scrollbar
diary_text.configure(yscrollcommand=diary_scrollbar.set)

# Pre-write header in diary text box
now = datetime.now()
date_str = now.strftime("%Y-%m-%d")
day_str = now.strftime("%A")
time_str = now.strftime("%I:%M %p")
diary_text.insert("1.0", f"Date: {date_str}\nDay: {day_str}\nTime: {time_str}\n\nDear Diary,\n")

# Buttons
button_frame = tk.Frame(diary_frame, bg="#FFF5E4")
button_frame.pack(pady=10)

tk.Button(button_frame, text="Save Entry", font=("Arial", 14, "bold"),
          bg="#4CAF50", foreground="#333333", command=save_diary_entry).pack(side="left", padx=10)

tk.Button(button_frame, text="View All Entries", font=("Arial", 14, "bold"),
          bg="#2196F3", foreground="#333333", command=view_all_diary_entries).pack(side="left", padx=10)

frames["DIARY FRAME"] = diary_frame

# ---------------- Dashboard Frame ----------------
dashboard_frame = tk.Frame(container, bg="#FFF5E4")  # Light cream
dashboard_frame.place(relwidth=1, relheight=1)

# Dynamic date-time 
date_time_label = tk.Label(dashboard_frame, font=("Arial", 16), bg="#FFF5E4", foreground="#333333")
date_time_label.pack(pady=10)
update_datetime()  # start the dynamic clock

# Dashboard title
tk.Label(dashboard_frame, text="DASHBOARD", font=("Arial", 30, "bold"),
         foreground="#333333", bg="#FFF5E4").pack(pady=10)
tk.Label(dashboard_frame, text="Welcome to your Digital Wellbeing Dashboard!",
         font=("Arial", 16), foreground="#333333", bg="#FFF5E4").pack(pady=5)

# Last 5 Non-Neutral Moods 
tk.Label(dashboard_frame, text="YOUR LAST 5 MOODS", 
         font=("Arial", 16, "bold"), bg="#FFF5E4", foreground="#333333").pack(pady=10, anchor="w")

dashboard_mood_button_frame = tk.Frame(dashboard_frame, bg="#FFF5E4")
dashboard_mood_button_frame.pack(pady=5, fill="x")

# Last 5 Neutral Messages 
neutral_message_container = tk.Frame(dashboard_frame, bg="#FFF5E4")
neutral_message_container.pack(pady=10, fill="both", expand=True)

neutral_message_inner_frame, neutral_message_canvas = make_scrollable_frame(neutral_message_container)
tk.Label(neutral_message_inner_frame, text="YOUR LAST 5 MESSAGES",
         font=("Arial", 16, "bold"), bg="#FFF5E4", fg = "#333333").pack(anchor="w", padx=5, pady=5)

# Last 5 Diary Entries 
diary_container = tk.Frame(dashboard_frame, bg="#FFF5E4")
diary_container.pack(pady=10, fill="both", expand=True)

diary_inner_frame, diary_canvas = make_scrollable_frame(diary_container)
tk.Label(diary_inner_frame, text="YOUR LAST 5 ENTRIES",
         font=("Arial", 16, "bold"), bg="#FFF5E4", fg = "#333333").pack(anchor="w", padx=5, pady=5)

load_dashboard_frame() # Show initial data

frames["DASHBOARD FRAME"] = dashboard_frame

# ---------------- Journal Frame ----------------
journal_frame = tk.Frame(container, bg="#E8F5E9")    # Soft green
journal_frame.place(relwidth=1, relheight=1)

tk.Label(journal_frame, text = "JOURNAL", font=("Arial", 30, "bold"),foreground = "#333333",bg="#E8F5E9").pack(pady=50)
tk.Label(journal_frame, text="Welcome to your journaling Dashboard!",
         font=("Arial", 16), foreground = "#333333", bg="#E8F5E9").pack(pady=20)

tk.Label(journal_frame, text = "YOUR MOOD TODAY", font = ("Arial"), foreground = "#333333",bg="#E8F5E9", justify="left", anchor="w").pack()
tk.Label(journal_frame, text="Select your current mood:",
         font=("Arial", 16),
         foreground="#333333", bg="#E8F5E9").pack(pady=10)

# Mood Buttons 
moods = {
    "Happy 😃": "#FFD700",
    "Excited 🤩": "#FFA500",
    "High Energy 😄": "#FFC107",
    "Calm 😌": "#A5D6A7",
    "Low 😔": "#90AFC5",
    "Angry 😡": "#EF9A9A",
    "Tired 😴": "#B0B0B0",
    "Anxious 😟": "#C4C3D0",
    "Confused 😕": "#F5DEB3",
    "Surprised 😲": "#81D4FA",
    "Lonely 😞": "#D3CCE3",
    "Grateful 🙏": "#FFF9C4",
    "Motivated 💪": "#66BB6A",
    "Playful 😜": "#F48FB1",
    "Bored 😐": "#E0E0E0"
}

# Frame for mood buttons
mood_buttons_frame = tk.Frame(journal_frame, bg="#E8F5E9")
mood_buttons_frame.pack(pady=20)

# Place buttons in grid or left packing inside this frame
for i, (mood, color) in enumerate(moods.items()):
    tk.Button(mood_buttons_frame, text=mood,
              font=("Arial", 14, "bold"),
              bg=color, fg = "#333333", width=10, height=2,
              relief="raised",
              command=lambda m=mood: save_mood(m)
              ).grid(row=i//4, column=i%4, padx=10, pady=10)  # 4 buttons per row

# Now your text box and label will appear below
tk.Label(journal_frame, text="Write your feelings:", font=("Arial", 14), bg="#E8F5E9", fg = "#333333").pack(pady=5)
feeling_text = tk.Text(journal_frame, height=5, width=50, font=("Arial", 12))
feeling_text.pack(pady=5)

submit_btn = tk.Button(journal_frame, text="Submit Feeling",
                       font=("Arial", 14, "bold"),
                       bg="#4CAF50", foreground="#333333",
                       command=submit_feeling)
submit_btn.pack(pady=10)

frames["JOURNAL FRAME"] = journal_frame 

# ---------------- statistics Frame ----------------
statistics_frame = tk.Frame(container, bg="#FCE4EC")  # Light pink
statistics_frame.place(relwidth=1, relheight=1)

# Add a label at top
tk.Label(statistics_frame, text="STATISTICS", font=("Arial", 30, "bold"),
         foreground="#333333", bg="#FCE4EC").pack(pady=20)

# Create scrollable frame inside statistics_frame
scroll_statistics, scroll_canvas = make_scrollable_frame(statistics_frame)

# Welcome label inside scroll_statistics
tk.Label(scroll_statistics, text="Welcome to your statistics Dashboard!",
         font=("Arial", 16), foreground="#333333", bg="#FCE4EC").pack(pady=20, anchor="w", padx=10)

# Time period options 
time_options = {
    "7 days": 7,
    "1 month": 30,
    "3 months": 90,
    "6 months": 180,
    "1 year": 365,
    "2 years": 730,
    "5 years": 1825,
    "Full history": None  # None means no filtering
}

selected_period = tk.StringVar()
selected_period.set("Full history")  # default

period_menu = ttk.OptionMenu(scroll_statistics, selected_period, *time_options.keys())
period_menu.pack(pady=10, anchor="w", padx=10)

# Button to plot
tk.Button(scroll_statistics, text="Show Mood Graph", font=("Arial", 14),
          bg="#4CAF50", foreground="#333333",
          command=lambda: plot_mood_graph(selected_period.get())).pack(pady=10, anchor="w", padx=10)

# Mood count frame
mood_count_frame = tk.Frame(scroll_statistics, bg="#FCE4EC")
mood_count_frame.pack(fill="x", pady=10, padx=10)  # always visible

update_mood_counts_buttons() # Call this function once to show counts immediately

frames["STATISTICS FRAME"] = statistics_frame

# ---------------- admin Frame ----------------
admin_frame = tk.Frame(container, bg="#FFF8E1")
admin_frame.place(relwidth=1, relheight= 1)

admin_login_frame = tk.Frame(admin_frame, bg="#FFF8E1")
admin_login_frame.place(relwidth=1, relheight=1)
frames["ADMIN_LOGIN"] = admin_login_frame

tk.Label(admin_login_frame, text="ADMIN LOGIN", font=("Arial", 26, "bold"),
         fg="#333333", bg="#FFF8E1").pack(pady=30)

tk.Label(admin_login_frame, text="USERNAME", font=("Arial", 12),
         fg="#333333", bg="#FFF8E1").pack()
adminusername_entry = tk.Entry(admin_login_frame, font=("Arial", 14))
adminusername_entry.pack(pady=10)

tk.Label(admin_login_frame, text="6-DIGIT-OTP", font=("Arial", 12),
         fg="#333333", bg="#FFF8E1").pack()
adminpassword_entry = tk.Entry(admin_login_frame, font=("Arial", 14), show="*")
adminpassword_entry.pack(pady=10)

# Admin Login Button
tk.Button(
    admin_login_frame,
    text="LOGIN",
    font=("Arial", 14, "bold"),
    bg="#4CAF50",
    fg="#333333",
    activebackground="#45a049",
    activeforeground="#FFF8E1",
    command=lambda: login_admin()  # call your login function
).pack(pady=20)

message_label = tk.Label(admin_login_frame, text="", font=("Arial", 12),
                         fg="red", bg="#FFF8E1")
message_label.pack(pady=5)

#  ADMIN DASHBOARD FRAME 
admin_dashboard_frame = tk.Frame(admin_frame, bg="#E8F5E9")
frames["ADMIN_DASHBOARD"] = admin_dashboard_frame

tk.Label(admin_dashboard_frame, text="ADMIN DASHBOARD", font=("Arial", 26, "bold"),
         fg="#2E7D32", bg="#E8F5E9").pack(pady=20)

tk.Button(admin_dashboard_frame, text="Refresh Tables", font=("Arial", 12, "bold"),
          bg="#4CAF50", fg="#333333", command=lambda: refresh_tables()).pack(pady=5)    # Refresh button

# Users Table Frame
users_frame = tk.LabelFrame(admin_dashboard_frame, text="All Users", font=("Arial", 14, "bold"),
                            bg="#E8F5E9", fg="#333333", padx=5, pady=5)
users_frame.pack(fill="x", padx=20, pady=10)

# Create Treeview
users_table = ttk.Treeview(users_frame, columns=("ID", "Username", "Password"), show="headings", height=5)
for col, width in zip(("ID", "Username", "Password"), (150, 250, 250)):
    users_table.heading(col, text=col)
    users_table.column(col, width=width, anchor="center")
users_table.pack(side="left", fill="both", expand=True)

# Attach vertical scrollbar
users_scrollbar = ttk.Scrollbar(users_frame, orient="vertical", command=users_table.yview)
users_scrollbar.pack(side="right", fill="y")
users_table.configure(yscrollcommand=users_scrollbar.set)

# Activity Table Frame
activity_frame = tk.LabelFrame(admin_dashboard_frame, text="User Activities", font=("Arial", 14, "bold"),
                               bg="#E8F5E9", fg="#333333", padx=5, pady=5)
activity_frame.pack(fill="both", expand=True, padx=20, pady=10)

# Create Treeview
columns = ("Time", "User", "Mood", "Message", "Diary")
activity_table = ttk.Treeview(activity_frame, columns=columns, show="headings", height=15)
for col in columns:
    activity_table.heading(col, text=col)
    activity_table.column(col, width=150, anchor="center")
activity_table.pack(side="left", fill="both", expand=True)

# Attach vertical scrollbar directly to the Treeview
activity_scrollbar = ttk.Scrollbar(activity_frame, orient="vertical", command=activity_table.yview)
activity_scrollbar.pack(side="right", fill="y")
activity_table.configure(yscrollcommand=activity_scrollbar.set)

# ---------- PLACE ALL FRAMES ----------
# Place all user frames (login, create account, dashboard, etc.)
for name, frame in frames.items():
    if name not in ["ADMIN FRAME"]:  
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)

show_frame("ADMIN_LOGIN") # Show the admin login frame first
frames["ADMIN FRAME"] = admin_frame

# ---------- MENU BUTTON ---------- 
# For menu icon  VERSATILE IMAGE PATHS FOR ANY DEVICE
# Open the image
menu_path = os.path.join(BASE_DIR, "PICS", "menu_icon.jpg")
menu_img = Image.open(menu_path)

# Resize the image
menu_img = menu_img.resize((20, 20), Image.LANCZOS)

# Convert to PhotoImage
menu_photo = ImageTk.PhotoImage(menu_img)

menu = tk.Menu(root, tearoff=0, bg="white", foreground="#333333", font=("Arial", 12))
menu.add_command(label="DASHBOARD", command=lambda: show_frame("DASHBOARD FRAME"))
menu.add_command(label="JOURNAL", command=lambda: show_frame("JOURNAL FRAME"))
menu.add_command(label="STATISTICS", command=lambda: show_frame("STATISTICS FRAME"))
menu.add_command(label="DIARY", command=lambda: show_frame ("DIARY FRAME"))
menu.add_command(label="ADMIN MODE", command=lambda: show_frame("ADMIN FRAME"))
menu.add_command(label="LOGOUT", command=logout)
menu.add_separator()  # adds a line separator for neatness
menu.add_command(label="Exit", command=root.quit)

# ---------------- show menu button ----------------
menu_button = tk.Button(
    container,  # parent is the container that holds all frames
    image=menu_photo,
    bg="#DCDCDC", fg = "#333333",
    borderwidth=0,
    command=lambda: menu.post(
        menu_button.winfo_rootx(),
        menu_button.winfo_rooty() + menu_button.winfo_height()
    )
)
menu_button.place(x=10, y=10)
menu_button.lift()

admin_dashboard_frame.place_forget()

menu_button.place(x=10, y=10)
menu_button.lift()

admin_dashboard_frame.place_forget()

# ---- First-run admin OTP setup ----
if OTP_IS_NEW:
    messagebox.showinfo(
        "Admin setup",
        "Add this key to Google Authenticator / Authy "
        "(Add account > Enter a setup key, time-based):\n\n" + OTP_SECRET
    )

show_frame("LOGIN FRAME")  # Show login frame first
root.lift()
root.focus_force()
root.mainloop()
conn.close()