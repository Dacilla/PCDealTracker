# A list of known PC hardware brands.
# Sorting by length in descending order helps match longer names first 
# (e.g., "Western Digital" before "WD").
KNOWN_BRANDS = [
    "AMD", "Intel", "NVIDIA", "Gigabyte", "ASUS", "MSI", "EVGA", "Zotac",
    "Sapphire", "PowerColor", "XFX", "ASRock", "Corsair", "G.Skill",
    "Kingston", "Crucial", "Samsung", "Seagate", "Western Digital", "WD",
    "Noctua", "be quiet!", "Cooler Master", "Lian Li", "Fractal Design",
    "Phanteks", "NZXT", "Seasonic", "Super Flower", "Antec", "Thermaltake",
    "Logitech", "Razer", "SteelSeries", "HyperX", "BenQ", "LG", "Dell",
    "Acer", "ViewSonic", "AOC"
]
KNOWN_BRANDS.sort(key=len, reverse=True)

def parse_product_name(name: str) -> dict:
    """
    Parses a product name string to extract structured data like brand and model.

    Args:
        name: The product name string.

    Returns:
        A dictionary containing the extracted 'brand' and 'model'.
    """
    parsed_data = {
        "brand": None,
        "model": name, # Default model to the full name
    }

    # --- Brand Identification ---
    # First, check for the brand anywhere in the name, surrounded by spaces.
    # This is a more reliable check for multi-word names.
    found_brand = None
    for brand in KNOWN_BRANDS:
        # Use word boundaries to avoid matching "Acer" in "Racer"
        if f" {brand.lower()} " in f" {name.lower()} ":
             found_brand = brand
             break
    
    # If not found, check if the name starts with a known brand.
    if not found_brand:
        for brand in KNOWN_BRANDS:
            if name.lower().startswith(brand.lower()):
                found_brand = brand
                break

    # --- Model Extraction ---
    if found_brand:
        parsed_data["brand"] = found_brand
        # The model is typically the rest of the string after the brand.
        # This is a simple starting point; it can be refined later.
        model_str = name.replace(found_brand, "", 1).strip()
        parsed_data["model"] = model_str

    return parsed_data
