# PCDealTracker

A web application for tracking PC hardware prices across Australian retailers. The project monitors multiple stores to identify price changes, sales, and historical low prices for computer components.

## Purpose

This tool addresses the lack of comprehensive price tracking for PC hardware in the Australian market. While sites like PCPartPicker exist, they don't clearly highlight when components go on sale or reach record low prices. PCDealTracker aims to fill this gap by providing clear indicators for deals and maintaining detailed price history.

## Features

- Price tracking across multiple Australian PC retailers
- Historical price data with visual charts
- Detection of sales and record low prices
- Search and filtering by component category
- Web interface for browsing current deals

## Supported Retailers

- PC Case Gear
- Scorptec
- Centre Com
- MSY Technology
- Umart
- Computer Alliance
- JW Computers
- Shopping Express
- Austin Computers
- BudgetPC

## System Requirements

- Python 3.11+ (3.13 recommended)
- Rust (for some Python package dependencies)
- Git
- Visual Studio Build Tools (Windows)

## Quick Start

### Using Docker
```bash
git clone https://github.com/YOUR_USERNAME/pcdealtracker.git
cd pcdealtracker
cp .env.example .env
docker-compose up -d
```

Visit http://localhost:3000 to view the application.

### Manual Setup
```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/pcdealtracker.git
cd pcdealtracker

# Set up backend environment
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Run backend
python app/main.py

# Run frontend (in another terminal)
cd frontend
python -m http.server 3000
```

Visit http://localhost:3000 to view the application.

## Development

### Project Structure
- `frontend/` - HTML/JavaScript frontend interface
- `backend/` - FastAPI backend with web scrapers and database
- `docs/` - Documentation
- `tests/` - Test suites

### Requirements
- Python 3.11 or higher
- Rust (required for some Python dependencies)
- Git

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for development setup and guidelines.

## Development Status

This is currently a personal project in early development. The current implementation includes a frontend prototype demonstrating the intended user interface and functionality.

## Planned Implementation

- FastAPI backend for data management and API endpoints
- Web scrapers for individual retailer sites
- SQLite database for development, PostgreSQL for production
- Automated price monitoring with scheduled updates
- Price change detection algorithms

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Disclaimer

This project is for educational and personal use. Please respect retailers' terms of service and implement appropriate rate limiting when scraping.