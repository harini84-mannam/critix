# 🎬 Critix - Movie Review Platform

Critix is a web-based movie review application that allows users to explore movies, view posters, and manage movie reviews through an interactive interface.

Built using **Python Django**, Critix provides a structured platform for storing movie information, displaying visual content, and managing user-focused movie reviews.

---

## ✨ Features

### 🎥 Movie Management

- Browse available movies
- View movie details
- Display movie posters
- Store movie information efficiently

### ⭐ Review System

- Add and manage movie reviews
- View audience opinions
- Maintain organized review data

### 🖼️ Media Support

- Upload and display movie posters
- Manage static and media files using Django

### 🛠️ Django Powered

- MVC/MVT architecture
- SQLite database integration
- Template-based frontend rendering
- Easy local deployment

---

# 🚀 Getting Started

Follow these steps to run Critix locally.

## Prerequisites

Make sure you have:

- Python 3.8+
- pip
- Virtual environment (recommended)

---

## 📥 Clone Repository

```bash
git clone https://github.com/harini84-mannam/critix.git

cd critix
```

---

## 🐍 Create Virtual Environment

### Windows

```bash
python -m venv venv

venv\Scripts\activate
```

### Linux / macOS

```bash
python3 -m venv venv

source venv/bin/activate
```

---

## 📦 Install Dependencies

Install required packages:

```bash
pip install -r requirements.txt
```

If requirements file is not available:

```bash
pip install django
```

---

# ⚙️ Database Setup

Apply migrations:

```bash
python manage.py makemigrations

python manage.py migrate
```

---

# 👤 Create Admin Account

Create a Django admin user:

```bash
python manage.py createsuperuser
```

Enter:

- Username
- Email
- Password

---

# ▶️ Run Application

Start the development server:

```bash
python manage.py runserver
```

Open your browser:

```
http://127.0.0.1:8000/
```

---

# 📁 Project Structure

```
critix/
│
├── manage.py                 # Django project manager
├── install.py                # Installation helper
├── db.sqlite3                # SQLite database
│
├── movie_review/             # Main Django application
│
├── media/
│   └── posters/              # Movie poster uploads
│
├── templates/                # HTML templates
│
├── static/                   # CSS, JS, static assets
│
└── README.md
```

---

# 🧰 Technology Stack

## Backend

- Python
- Django

## Database

- SQLite

## Frontend

- HTML
- CSS
- Django Templates

## Media Handling

- Django Media Files
- Image Upload Management

---

# 🔑 Django Features Used

- Models for database management
- Views for application logic
- Templates for UI rendering
- URL routing
- Static and media file handling
- Django ORM

---

# 📸 Screenshots

Add application screenshots here:

```
screenshots/
├── home.png
├── movie_details.png
└── reviews.png
```

Example:

![Home Page](screenshots/home.png)

---

# 🔮 Future Enhancements

Possible improvements:

- User authentication
- Movie ratings system
- Search functionality
- Movie recommendations
- API integration with movie databases
- User profiles
- Comments and discussions
- Dark mode UI

---

# 🤝 Contributing

Contributions are welcome!

Steps:

1. Fork this repository

2. Create a new branch:

```bash
git checkout -b feature-name
```

3. Commit changes:

```bash
git commit -m "Add new feature"
```

4. Push changes:

```bash
git push origin feature-name
```

5. Open a Pull Request

---

# 📄 License

This project is open-source and available under the MIT License.

---

# 👩‍💻 Author

**Harini Mannam**

GitHub:
https://github.com/harini84-mannam

---

⭐ If you like this project, consider giving it a star!
