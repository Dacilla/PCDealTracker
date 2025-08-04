import re

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

def _parse_cpu(name: str) -> dict:
    """Parses attributes for a CPU name."""
    attributes = {}
    name_lower = name.lower()

    # Socket
    if "am5" in name_lower:
        attributes["socket"] = "AM5"
    elif "am4" in name_lower:
        attributes["socket"] = "AM4"
    elif "lga1700" in name_lower or "1700" in name_lower:
        attributes["socket"] = "LGA1700"
    elif "lga1200" in name_lower or "1200" in name_lower:
        attributes["socket"] = "LGA1200"

    # Series (Intel)
    if "i9" in name_lower:
        attributes["series"] = "Core i9"
    elif "i7" in name_lower:
        attributes["series"] = "Core i7"
    elif "i5" in name_lower:
        attributes["series"] = "Core i5"
    elif "i3" in name_lower:
        attributes["series"] = "Core i3"
    
    # Series (AMD)
    if "ryzen 9" in name_lower:
        attributes["series"] = "Ryzen 9"
    elif "ryzen 7" in name_lower:
        attributes["series"] = "Ryzen 7"
    elif "ryzen 5" in name_lower:
        attributes["series"] = "Ryzen 5"
    elif "ryzen 3" in name_lower:
        attributes["series"] = "Ryzen 3"

    return attributes

def _parse_gpu(name: str) -> dict:
    """Parses attributes for a Graphics Card name."""
    attributes = {}
    
    # VRAM
    vram_match = re.search(r'(\d+)\s*GB', name, re.IGNORECASE)
    if vram_match:
        attributes["vram_gb"] = int(vram_match.group(1))

    # Series
    if "rtx" in name.lower():
        attributes["series"] = "RTX"
    elif "rx" in name.lower():
        attributes["series"] = "RX"
    elif "arc" in name.lower():
        attributes["series"] = "Arc"

    return attributes

def _parse_monitor(name: str) -> dict:
    """Parses attributes for a Monitor name."""
    attributes = {}
    name_lower = name.lower()

    # Screen Size
    size_match = re.search(r'(\d{2}(\.\d)?)\s*(inch|\")', name, re.IGNORECASE)
    if size_match:
        attributes["screen_size_inch"] = float(size_match.group(1))

    # Resolution
    if "4k" in name_lower or "2160p" in name_lower:
        attributes["resolution"] = "4K"
    elif "1440p" in name_lower or "qhd" in name_lower:
        attributes["resolution"] = "1440p"
    elif "1080p" in name_lower or "fhd" in name_lower:
        attributes["resolution"] = "1080p"

    # Panel Type
    if "ips" in name_lower:
        attributes["panel_type"] = "IPS"
    elif "va" in name_lower:
        attributes["panel_type"] = "VA"
    elif "oled" in name_lower:
        attributes["panel_type"] = "OLED"
    elif "tn" in name_lower:
        attributes["panel_type"] = "TN"

    return attributes

def parse_product_attributes(name: str, category_name: str) -> dict:
    """
    Top-level parser that routes to a category-specific parser.
    """
    category_name = category_name.lower()
    
    if "cpu" in category_name:
        return _parse_cpu(name)
    if "graphics" in category_name:
        return _parse_gpu(name)
    if "monitor" in category_name:
        return _parse_monitor(name)
        
    return {} # Return empty dict for categories with no specific parser yet

def parse_product_name(name: str) -> dict:
    """
    Parses a product name string to extract basic data like brand and model.
    """
    parsed_data = {
        "brand": None,
        "model": name, # Default model to the full name
    }

    found_brand = None
    for brand in KNOWN_BRANDS:
        if f" {brand.lower()} " in f" {name.lower()} ":
             found_brand = brand
             break
    
    if not found_brand:
        for brand in KNOWN_BRANDS:
            if name.lower().startswith(brand.lower()):
                found_brand = brand
                break

    if found_brand:
        parsed_data["brand"] = found_brand
        model_str = name.replace(found_brand, "", 1).strip()
        parsed_data["model"] = model_str

    return parsed_data
