"""Generate deterministic sample CSVs (English / Tamil / Tanglish). Run: python generate_sample_data.py"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

# (text, rating) pools. Mix of English, Tamil script and Tanglish.
POSITIVE = [
    ("Biryani was amazing, packing also neat. Will order again!", 5),
    ("Taste super, portion also good. Value for money.", 5),
    ("Delivery boy was very polite and food came hot.", 5),
    ("Loved the paneer butter masala, perfectly cooked.", 5),
    ("Great service, staff were friendly and quick.", 4),
    ("Packaging was spill-proof and neat. Impressed.", 4),
    ("Food was fresh and tasty. Quick delivery too.", 4),
    ("Biryani semma taste! Packing um romba nalla irundhuchu.", 5),
    ("Saapadu romba nalla irundhuchu, delivery um on time. Thanks!", 5),
    ("Chicken 65 vera level, kandippa thirumba order panuven.", 5),
    ("Staff romba friendly, seat um clean ah irundhuchu.", 4),
    ("Price ku worth ah irukku, quantity nalla irukku.", 4),
    ("பிரியாணி மிகவும் சுவையாக இருந்தது. மீண்டும் வருவேன்!", 5),
    ("உணவு சூடாகவும் சுவையாகவும் இருந்தது. நன்றி.", 5),
    ("பணியாளர்கள் மிகவும் மரியாதையாக நடந்துகொண்டனர்.", 4),
    ("பேக்கிங் அருமை, எதுவும் சிந்தவில்லை.", 4),
]
NEUTRAL = [
    ("Food was okay, nothing special. Average taste.", 3),
    ("Decent biryani but nothing extraordinary.", 3),
    ("App works fine but search is slow sometimes.", 3),
    ("Delivery was on time, food was just average.", 3),
    ("Food okay than, ethir paarthathu alavukku illa.", 3),
    ("Taste paravalla, but konjam salt jaasthi.", 3),
    ("App ok, but offers ellam clear ah theriyala.", 3),
    ("உணவு பரவாயில்லை, சராசரி சுவை.", 3),
    ("டெலிவரி சரியான நேரத்தில் வந்தது, சுவை சாதாரணம்.", 3),
]
NEGATIVE = [
    # delivery
    ("Ordered at 8pm, came at 9:10. Food fully cold. Very bad.", 1),
    ("Delivery took almost 90 minutes. Never again.", 1),
    ("Delivery partner was late and the food was cold.", 2),
    ("Order romba late ah vandhuchu, saapadu fully thanda irundhuchu.", 1),
    ("1 maninerathukku mela aachu delivery ku, cold food.", 1),
    ("டெலிவரி மிகவும் தாமதம், உணவு குளிர்ந்து போய் இருந்தது.", 1),
    # price
    ("Saapadu nalla irundhuchu but bill la extra charge pottanga", 2),
    ("Packing charge and service charge not shown on menu. Hidden charges!", 2),
    ("Too expensive for the small portion size.", 2),
    ("Rate romba jaasthi, quantity romba kammi.", 2),
    ("பில்லில் கூடுதல் கட்டணம் சேர்த்துள்ளனர், விலை அதிகம்.", 2),
    # packaging
    ("Gravy spilled all over the bag. Poor packing.", 2),
    ("Packing sariya illa, curry ellam kottiduchu.", 2),
    ("பேக்கிங் சரியில்லை, சாப்பாடு சிந்திவிட்டது.", 2),
    # app
    ("App keeps crashing at payment. Wasted 20 minutes.", 2),
    ("Offer code work aagala, app la bug irukku.", 2),
    ("ஆப் அடிக்கடி ஹேங் ஆகிறது, ஆர்டர் போடவே முடியவில்லை.", 2),
    # food quality (non-urgent)
    ("Biryani was dry and too salty. Disappointed.", 2),
    ("Chicken sariya vegala, half cooked pola irundhuchu.", 2),
    ("சுவை மிகவும் மோசம், உணவு சரியாக வேகவில்லை.", 1),
    # staff (non-urgent)
    ("Waiter ignored us for 20 minutes. Slow service.", 2),
    ("Service romba slow, staff kitta ketta kooda gavanikala.", 2),
]
URGENT = [
    ("Got food poisoning after eating the chicken biryani. Vomiting all night. Terrible!", 1),
    ("My kid fell sick after eating here, stomach pain and vomiting. Food was stale.", 1),
    ("Saapitta apram vayiru valikuthu, vomit aachu. Food poisoning maari irukku!", 1),
    ("Found a hair in my food and the manager laughed it off. Want a refund.", 1),
    ("Wrong order delivered, I ordered veg but got chicken. I am vegetarian! Want refund.", 1),
    ("Veg order kudutha non-veg anuppitanga. Romba mosam, refund venum.", 1),
    ("Completely wrong order delivered and nobody answers the phone.", 1),
    ("Staff was extremely rude and shouted at us in front of everyone.", 1),
    ("Waiter rude ah pesunaaru, romba mosamana nadathai. Manager kitta sonnaalum use illa.", 1),
    ("ஊழியர்கள் மிகவும் அநாகரிகமாக நடந்துகொண்டனர், கத்தினார்கள்.", 1),
    ("சாப்பிட்ட பிறகு வாந்தி, வயிற்று வலி. உணவு கெட்டுப்போயிருந்தது!", 1),
    ("தவறான ஆர்டர் வந்தது, பணத்தை திருப்பி தர வேண்டும்.", 1),
]

PLATFORMS = ["Zomato", "Swiggy", "Google", "Amazon"]


def build(start: date, n: int, id_start: int, rng: random.Random, weights, urgent_n: int):
    rows = []
    pools = [POSITIVE, NEUTRAL, NEGATIVE]
    texts = []
    for _ in range(n - urgent_n):
        pool = rng.choices(pools, weights=weights)[0]
        texts.append(rng.choice(pool))
    for _ in range(urgent_n):
        texts.append(rng.choice(URGENT))
    rng.shuffle(texts)
    for i, (text, rating) in enumerate(texts):
        d = start + timedelta(days=rng.randint(0, 6))
        rows.append([f"R-{id_start + i}", d.isoformat(), rng.choice(PLATFORMS), rating, text])
    rows.sort(key=lambda r: (r[1], r[0]))
    return rows


def write(path: Path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["review_id", "date", "platform", "rating", "review_text"])
        w.writerows(rows)


def main():
    out = Path(__file__).parent / "data"
    out.mkdir(exist_ok=True)
    rng = random.Random(40)
    cur = build(date(2026, 9, 28), 220, 1001, rng, [0.50, 0.15, 0.35], urgent_n=11)
    prev = build(date(2026, 9, 21), 90, 901, rng, [0.55, 0.15, 0.30], urgent_n=4)
    write(out / "reviews_week40.csv", cur)
    write(out / "reviews_week39.csv", prev)
    print(f"Wrote {len(cur)} rows to reviews_week40.csv and {len(prev)} rows to reviews_week39.csv")


if __name__ == "__main__":
    main()
