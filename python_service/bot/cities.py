"""
Known cities for location extraction.
Add new cities here as your business expands — one city per line, lowercase.
"""

KNOWN_CITIES = [
    # ── Tamil Nadu ────────────────────────────────────────────────────────
    "chennai", "coimbatore", "madurai", "trichy", "salem", "tiruppur",
    "erode", "vellore", "thoothukudi", "tirunelveli", "thanjavur",
    "karur", "dindigul", "kumbakonam", "hosur", "komarapalayam",
    "namakkal", "pudukkottai", "sivakasi", "pollachi", "udumalpet",
    "palani", "rajapalayam", "virudhunagar", "nagercoil", "kanchipuram",
    "tambaram", "avadi", "ambattur", "tiruvallur", "cuddalore",
    "villupuram", "kallakurichi", "perambalur", "ariyalur", "nagapattinam",
    "mayiladuthurai", "theni", "krishnagiri", "dharmapuri", "tiruvannamalai",
    "ranipet", "chengalpattu", "tenkasi", "tirupattur", "sivaganga",
    "ramanathapuram", "ooty", "kodaikanal",

    # ── Abbreviations ─────────────────────────────────────────────────────
    "cbe", "chn", "mdu", "blr", "hyd", "tvm",

    # ── Telangana ─────────────────────────────────────────────────────────
    "hyderabad", "warangal", "nizamabad", "karimnagar", "khammam",
    "mahbubnagar", "nalgonda", "adilabad", "suryapet", "siddipet",
    "miryalaguda", "jagtial", "mancherial", "ramagundam", "secunderabad",
    "sangareddy", "medak",

    # ── Andhra Pradesh ────────────────────────────────────────────────────
    "vijayawada", "visakhapatnam", "vizag", "guntur", "nellore",
    "kurnool", "rajahmundry", "tirupati", "kakinada", "anantapur",
    "kadapa", "ongole", "eluru", "bhimavaram", "machilipatnam",
    "srikakulam", "vizianagaram", "chittoor", "hindupur", "tenali",
    "narasaraopet", "proddatur", "tadipatri", "guntakal", "adoni",
    "nandyal", "tadepalligudem", "amalapuram", "palasa", "bapatla",

    # ── Kerala ────────────────────────────────────────────────────────────
    "kochi", "trivandrum", "kozhikode", "thrissur", "kollam",
    "palakkad", "malappuram", "kannur", "kottayam", "alappuzha",
    "ernakulam", "calicut", "kasaragod", "pathanamthitta", "idukki", "wayanad",

    # ── Karnataka ─────────────────────────────────────────────────────────
    "bangalore", "bengaluru", "mysore", "mysuru", "hubli", "mangalore",
    "belgaum", "gulbarga", "bellary", "bijapur", "shimoga",
    "tumkur", "davangere", "udupi", "hassan", "mandya",
    "dharwad", "bagalkot", "raichur", "koppal", "gadag",
    "chikmagalur", "kodagu", "coorg", "hospet", "chitradurga",

    # ── Other major cities ────────────────────────────────────────────────
    "mumbai", "delhi", "pune", "kolkata", "ahmedabad", "surat",
    "jaipur", "lucknow", "kanpur", "nagpur", "indore", "bhopal",
]

# Normalise display names (city → what to show customer)
CITY_DISPLAY_OVERRIDES = {
    "bengaluru":       "Bangalore",
    "tiruchirappalli": "Trichy",
    "visakhapatnam":   "Vizag",
    "mysuru":          "Mysore",
    "calicut":         "Kozhikode",
}