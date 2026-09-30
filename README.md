# 🎬 Critix: Movie Review & Community Platform

Critix is a full-stack movie review platform built with Django. Users can discover movies, rate and review them, join threaded discussions, and keep watchlists, while a custom-built admin portal gives staff full control over content and moderation.

### 🔗 [Live Demo: critix-review.vercel.app](https://critix-review.vercel.app/)

![Django](https://img.shields.io/badge/Django-092E20?style=flat-square&logo=django&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=flat-square&logo=javascript&logoColor=black)
![HTML5](https://img.shields.io/badge/HTML5-E34F26?style=flat-square&logo=html5&logoColor=white)
![CSS3](https://img.shields.io/badge/CSS3-1572B6?style=flat-square&logo=css3&logoColor=white)
![Vercel](https://img.shields.io/badge/Vercel-000000?style=flat-square&logo=vercel&logoColor=white)

---

## ✨ Features

### 🍿 For Movie Lovers
- **Browse and discover** movies with posters, details and cast information
- **Filter by genre** (Action, Comedy, Drama, Thriller, Romance and more) and **sort** by Newest, Oldest, Top Rated, A-Z or Z-A
- **Movie of the Day** spotlight, plus **Trending Now** and **Coming Soon** sections for upcoming releases with trailer links
- **Rate and review** movies
- **Like reviews** and reply to them in **threaded conversations**
- **Watchlist** for movies you want to see and **Watched** list for ones you have seen
- **In-app notifications** about activity on your reviews
- **Report** inappropriate reviews

### 🛡️ Custom Admin Portal
A complete admin system built from scratch, instead of relying only on Django's default admin:

- **Dashboard** with an overview of the platform
- **Management screens** for movies, reviews, users and genres
- **Moderation** of reported reviews, with a history of report actions
- **Staff access control** to limit who can do what
- **Auto-discovering sidebar** that picks up newly added models automatically, so navigation links don't need to be hardcoded
- **Metadata-driven dynamic views** with list filtering and sorting
- **CSV / Excel import and export**, with foreign-key resolution on import
- **Bulk actions**, plus import and delete confirmation pages
- Admin notifications

---

## 🧰 Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Django |
| Database | PostgreSQL (Neon) |
| Frontend | HTML, CSS, JavaScript, Django templates |
| Movie data and posters | TMDB |
| Hosting | Vercel |

---

## 🚀 Getting Started

### Prerequisites
- Python 3.9+
- PostgreSQL (or SQLite for local development)

### Installation

```bash
# Clone the repository
git clone https://github.com/harini84-mannam/<repo-name>.git
cd <repo-name>

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables (see below)

# Apply migrations and create an admin user
python manage.py migrate
python manage.py createsuperuser

# Run the development server
python manage.py runserver
```

Then open http://127.0.0.1:8000/ in your browser.

### Environment variables

Create a `.env` file (or set these in your hosting dashboard):

```env
SECRET_KEY=your-django-secret-key
DEBUG=True
DATABASE_URL=postgres://user:password@host:5432/dbname
```

Add any other keys your project uses, such as a TMDB API key.

---

## 🌐 Deployment

The live site is deployed on **Vercel** with a **Neon PostgreSQL** database.

---

## 📸 Screenshots

<!-- Add screenshots here, for example:
![Home Page](screenshots/home.png)
![Movie Details and Reviews](screenshots/movie-detail.png)
![Admin Dashboard](screenshots/admin-dashboard.png)
-->

---

## 👩‍💻 Author

**Harini Mannam**
[Portfolio](https://hariniport-hwshwlfa.manus.space/) · [LinkedIn](https://www.linkedin.com/in/harini-mannam-052aa730b/) · [GitHub](https://github.com/harini84-mannam)

Built during my Software Development Internship at Meslova Systems.
