# Rainy Road

## This script will show in a map if it is raining in a route between two cities.

It uses mainly **osmnx** (with networkx). You can get the app that uses this script as an server [here](https://github.com/rtalis/rainy-road-app/tree/main).

## Getting Started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/) (recommended)
- An [OpenWeather API key](https://home.openweathermap.org/api_keys) (free tier available)

### Quick Start with Docker (Recommended)

1. **Clone the repository:**

   ```bash
   git clone https://github.com/rtalis/rainy_road.git
   cd rainy_road
   ```

2. **Configure environment:**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and set your `OW_API_KEY`:

   ```bash
   OW_API_KEY=your_openweather_api_key_here
   ```

3. **Start all services:**

   ```bash
   docker compose up -d
   ```

4. **Access the API at** `http://localhost:8000`

5. **View logs:**

   ```bash
   docker compose logs -f
   ```

6. **Stop services:**
   ```bash
   docker compose down
   ```

### Environment Variables

Edit the `.env` file to customize your settings:

| Variable                | Description                                                                                                                  | Default          |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ---------------- |
| `OW_API_KEY`            | OpenWeather API key (required)                                                                                               | -                |
| `CORS_ORIGINS`          | Allowed CORS origins. Use `*` for all origins, or comma-separated list (e.g., `https://myapp.com,https://staging.myapp.com`) | `*`              |
| `GENERATED_MAPS_DIR`    | Directory to store generated map files                                                                                       | `generated_maps` |
| `MAP_MAX_AGE_SECONDS`   | Time in seconds before old maps are auto-deleted                                                                             | `7200` (2 hours) |
| `CELERY_RESULT_EXPIRES` | Time in seconds before Celery results expire                                                                                 | `7200`           |

### Docker Commands Reference

```bash
# Build and start all services
docker compose up -d --build

# View logs (all services)
docker compose logs -f

# View logs (specific service)
docker compose logs -f web
docker compose logs -f celery

# Restart services
docker compose restart

# Stop services
docker compose down

# Stop and remove volumes (clean slate)
docker compose down -v
```

---

## Manual Installation (Alternative)

If you prefer not to use Docker, you can run the application manually.

### Requirements

- Python 3.11+
- Redis server

### Installation

```bash
git clone https://github.com/rtalis/rainy_road.git
cd rainy_road
pip install -r requirements.txt
```

### Redis Setup

Install Redis for your distribution:

**Debian/Ubuntu:**

```bash
sudo apt install redis-server
sudo systemctl enable redis-server
sudo systemctl start redis-server
```

**Fedora/RHEL:**

```bash
sudo dnf install redis
sudo systemctl enable redis
sudo systemctl start redis
```

**macOS (Homebrew):**

```bash
brew install redis
brew services start redis
```

Verify Redis is running:

```bash
redis-cli ping
# Should return: PONG
```

### Running Manually

**Terminal 1 - Start the Flask server:**

```bash
set -a && source .env && set +a
flask run --host=0.0.0.0 --port=5000
```

**Terminal 2 - Start Celery worker:**

```bash
set -a && source .env && set +a
celery -A app.celery_app worker --loglevel=info
```

### Production Mode (with Gunicorn)

```bash
pip install gunicorn
set -a && source .env && set +a
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

---

## API Endpoints

| Endpoint              | Method | Description                                  |
| --------------------- | ------ | -------------------------------------------- |
| `/`                   | GET    | Redirects to GitHub repository               |
| `/generate_map`       | GET    | Generate map synchronously (legacy)          |
| `/generate_map_v2`    | GET    | Generate map asynchronously, returns task ID |
| `/progress/<task_id>` | GET    | Get progress of async map generation         |
| `/result/<task_id>`   | GET    | Get generated map file                       |

### Example Usage

**Synchronous (legacy):**

```
GET /generate_map?start_location=São Paulo,SP&end_location=Rio de Janeiro,RJ
```

**Asynchronous (recommended):**

```bash
# Start map generation
curl "http://localhost:8000/generate_map_v2?start_location=São Paulo,SP&end_location=Rio de Janeiro,RJ"
# Returns: {"task_id": "abc123..."}

# Check progress
curl "http://localhost:8000/progress/abc123..."
# Returns: {"state": "PROGRESS", "stage": "route", "percent": 75, ...}

# Get result when complete
curl "http://localhost:8000/result/abc123..."
# Returns: HTML map file
```

You can also try the [Rainy Road App](https://github.com/rtalis/rainy-road-app/tree/main), it uses this server as a backend.

## How it works

Set the names of the cities and a openwheather api key, it will find the shortest route between the places and show if it is raining on the road. The script uses osmnx to create a map, geopy for translate names to coordinates, networkx and scikit-learn for route, openweather for wheather data and folium to show it in a browser.
