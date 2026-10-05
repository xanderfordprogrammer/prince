# FIND MY MECH

Motorcycle shop finder, queue and reservation prototype (Flask + SQLite). Compare shops by busyness, wait time and prices, then join a queue or reserve before you go.

## Run locally
```bash
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000. The SQLite database (`database/findmymech.db`) and the sample data (4 shops, 10 services each, queue entries, accounts) are created automatically on first run. To reset, delete the `.db` file and run `python app.py` again.

## Demo accounts
| Role | Login | Password |
|---|---|---|
| Rider | demo@findmymech.test | demo123 |
| Shop owner (CDLM) | owner1@findmymech.test | admin123 |
| ANMAR / AGRT / PUG | owner2 / owner3 / owner4 @findmymech.test | admin123 |

## Notes
- Prices, availability, queues and locations are sample data. Cost estimates = base price x type x brand x model factors (`estimate()` in `app.py`).
- Distance uses `USER_LOCATION` in `app.py`; replace with browser GPS later. The shop-finder map is a placeholder fed by each shop's latitude/longitude.
- Set `SECRET_KEY` as an environment variable for anything beyond local demos. Not production-hardened (no CSRF tokens, no password reset).
