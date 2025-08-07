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

# List of common, non-essential keywords to remove during strict normalization
NORMALIZATION_STRIP_KEYWORDS_STRICT = [
    'OC', 'Edition', 'Gaming', 'Pro', 'Founders', 'Strix', 'TUF', 'ROG',
    'Aorus', 'Windforce', 'Eagle', 'Vision', 'Ventus', 'Suprim', 'Trio',
    'Graphics Card', 'CPU', 'Processor', 'Cooler', 'Black', 'White', 'RGB',
    'ARGB', 'DDR4', 'DDR5', 'GDDR6X', 'GDDR7', 'PCIe', 'Gen4', 'Gen5',
    'with Cooler', '(No Cooler)', 'WOF'
]

# A more aggressive list for loose normalization
NORMALIZATION_STRIP_KEYWORDS_LOOSE = NORMALIZATION_STRIP_KEYWORDS_STRICT + [
    'core', 'threads', 'ghz', 'matx', 'atx', 'itx', 'wifi'
]

def normalize_model_strict(model_string: str) -> str:
    """
    Cleans and standardizes a model string to improve matching across retailers.
    """
    if not model_string:
        return ""

    normalized = model_string.lower()
    for keyword in NORMALIZATION_STRIP_KEYWORDS_STRICT:
        normalized = normalized.replace(keyword.lower(), '')

    normalized = re.sub(r'\d+\s*(gb|mb|mhz|cl\d+)', '', normalized)
    normalized = re.sub(r'[^a-z0-9\s]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized

def normalize_model_loose(model_string: str) -> str:
    """
    A more aggressive normalization that strips out technical specs to find the core model.
    """
    if not model_string:
        return ""

    normalized = model_string.lower()
    for keyword in NORMALIZATION_STRIP_KEYWORDS_LOOSE:
        normalized = normalized.replace(keyword.lower(), '')
        
    # Remove specs like "6-core", "4.6ghz", etc.
    normalized = re.sub(r'\b\d+(\-|\s)?(core|thread|ghz|mhz|gb|mb)\b', '', normalized)
    
    normalized = re.sub(r'[^a-z0-9\s]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized

def _parse_cpu(name: str) -> dict:
    """Parses attributes for a CPU name."""
    attributes = {}
    name_lower = name.lower()

    # Socket
    if "am5" in name_lower: attributes["socket"] = "AM5"
    elif "am4" in name_lower: attributes["socket"] = "AM4"
    elif "lga1700" in name_lower or "1700" in name_lower: attributes["socket"] = "LGA1700"
    elif "lga1200" in name_lower or "1200" in name_lower: attributes["socket"] = "LGA1200"

    # Series (Intel)
    if "intel" in name_lower or attributes.get("socket") in ["LGA1700", "LGA1200"]:
        if "ultra 9" in name_lower: attributes["intel_series"] = "Core Ultra 9"
        elif "ultra 7" in name_lower: attributes["intel_series"] = "Core Ultra 7"
        elif "ultra 5" in name_lower: attributes["intel_series"] = "Core Ultra 5"
        elif "i9" in name_lower: attributes["intel_series"] = "Core i9"
        elif "i7" in name_lower: attributes["intel_series"] = "Core i7"
        elif "i5" in name_lower: attributes["intel_series"] = "Core i5"
        elif "i3" in name_lower: attributes["intel_series"] = "Core i3"
    
    # Series (AMD)
    if "amd" in name_lower or attributes.get("socket") in ["AM5", "AM4"]:
        if "ryzen 9" in name_lower: attributes["amd_series"] = "Ryzen 9"
        elif "ryzen 7" in name_lower: attributes["amd_series"] = "Ryzen 7"
        elif "ryzen 5" in name_lower: attributes["amd_series"] = "Ryzen 5"
        elif "ryzen 3" in name_lower: attributes["amd_series"] = "Ryzen 3"

    return attributes

def _parse_gpu(name: str) -> dict:
    """Parses attributes for a Graphics Card name."""
    attributes = {}
    name_lower = name.lower()
    
    # VRAM
    vram_match = re.search(r'(\d+)\s*GB', name, re.IGNORECASE)
    if vram_match:
        attributes["vram_gb"] = int(vram_match.group(1))

    # Series
    if "rtx" in name_lower: attributes["series"] = "RTX"
    elif "gtx" in name_lower: attributes["series"] = "GTX"
    elif "rx" in name_lower: attributes["series"] = "RX"
    elif "arc" in name_lower: attributes["series"] = "Arc"

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
    if "4k" in name_lower or "2160p" in name_lower: attributes["resolution"] = "4K"
    elif "1440p" in name_lower or "qhd" in name_lower: attributes["resolution"] = "1440p"
    elif "1080p" in name_lower or "fhd" in name_lower: attributes["resolution"] = "1080p"

    # Panel Type
    if "ips" in name_lower: attributes["panel_type"] = "IPS"
    elif "va" in name_lower: attributes["panel_type"] = "VA"
    elif "oled" in name_lower: attributes["panel_type"] = "OLED"
    elif "tn" in name_lower: attributes["panel_type"] = "TN"

    # Refresh Rate
    refresh_rate_match = re.search(r'(\d{2,3})\s*hz', name_lower)
    if refresh_rate_match:
        attributes["refresh_rate_hz"] = int(refresh_rate_match.group(1))

    # HDR Level
    if "hdr1000" in name_lower: attributes["hdr_level"] = "HDR1000"
    elif "hdr600" in name_lower: attributes["hdr_level"] = "HDR600"
    elif "hdr400" in name_lower: attributes["hdr_level"] = "HDR400"
    elif "dolby vision" in name_lower: attributes["hdr_level"] = "Dolby Vision"
    elif "hdr" in name_lower: attributes["hdr_level"] = "HDR"


    return attributes

def _parse_motherboard(name: str) -> dict:
    """Parses attributes for a Motherboard name."""
    attributes = {}
    name_lower = name.lower()

    # Socket
    if "am5" in name_lower: attributes["socket"] = "AM5"
    elif "am4" in name_lower: attributes["socket"] = "AM4"
    elif "lga1700" in name_lower: attributes["socket"] = "LGA1700"
    elif "lga1200" in name_lower: attributes["socket"] = "LGA1200"

    # Form Factor
    if "e-atx" in name_lower or "eatx" in name_lower: attributes["form_factor"] = "E-ATX"
    elif "atx" in name_lower and "micro-atx" not in name_lower: attributes["form_factor"] = "ATX"
    elif "micro-atx" in name_lower or "matx" in name_lower: attributes["form_factor"] = "Micro-ATX"
    elif "mini-itx" in name_lower or "mitx" in name_lower: attributes["form_factor"] = "Mini-ITX"

    # Chipset (Brand specific)
    intel_chipset_match = re.search(r'\b([ZBHXW]\d{3,4})\b', name, re.IGNORECASE)
    amd_chipset_match = re.search(r'\b([XBA]\d{3}E?)\b', name, re.IGNORECASE)

    if attributes.get("socket") in ["AM5", "AM4"] or "amd" in name_lower:
        if amd_chipset_match:
            attributes["amd_chipset"] = amd_chipset_match.group(1).upper()
    elif attributes.get("socket") in ["LGA1700", "LGA1200"] or "intel" in name_lower:
        if intel_chipset_match:
            attributes["intel_chipset"] = intel_chipset_match.group(1).upper()
    else:
        if intel_chipset_match:
            attributes["intel_chipset"] = intel_chipset_match.group(1).upper()
        elif amd_chipset_match:
            attributes["amd_chipset"] = amd_chipset_match.group(1).upper()

    return attributes

def _parse_ram(name: str) -> dict:
    """Parses attributes for Memory (RAM)."""
    attributes = {}
    name_lower = name.lower()

    # Type
    if "ddr5" in name_lower: attributes["type"] = "DDR5"
    elif "ddr4" in name_lower: attributes["type"] = "DDR4"
    
    # Capacity
    capacity_match = re.search(r'(\d+)\s*GB', name, re.IGNORECASE)
    if capacity_match:
        attributes["capacity_gb"] = int(capacity_match.group(1))

    # Speed
    speed_match = re.search(r'(\d{4,})\s*MHz', name, re.IGNORECASE)
    if speed_match:
        attributes["speed_mhz"] = int(speed_match.group(1))
    
    # Form Factor
    if "sodimm" in name_lower:
        attributes["form_factor"] = "SODIMM"
    else:
        attributes["form_factor"] = "Desktop"
        
    # ECC - Look for ECC but not non-ECC
    if re.search(r'\b(?<!non-)ecc\b', name_lower):
        attributes["ecc"] = "ECC"
    else:
        attributes["ecc"] = "Non-ECC"
        
    return attributes

def _parse_storage(name: str) -> dict:
    """Parses attributes for Storage (SSD/HDD)."""
    attributes = {}
    name_lower = name.lower()

    # Type
    if "nvme" in name_lower: attributes["type"] = "NVMe SSD"
    elif "ssd" in name_lower: attributes["type"] = "SATA SSD"
    elif "hdd" in name_lower or "hard drive" in name_lower: attributes["type"] = "HDD"

    # Capacity
    capacity_match = re.search(r'(\d+(\.\d)?)\s*(TB|GB)', name, re.IGNORECASE)
    if capacity_match:
        val = float(capacity_match.group(1))
        unit = capacity_match.group(3).upper()
        if unit == "TB":
            attributes["capacity_gb"] = int(val * 1000)
        else:
            attributes["capacity_gb"] = int(val)

    # Form Factor
    if "m.2" in name_lower: attributes["form_factor"] = "M.2"
    elif "2.5" in name: attributes["form_factor"] = '2.5"'
    elif "3.5" in name: attributes["form_factor"] = '3.5"'

    return attributes

def _parse_psu(name: str) -> dict:
    """Parses attributes for a Power Supply Unit (PSU)."""
    attributes = {}
    name_lower = name.lower()

    # Wattage
    wattage_match = re.search(r'(\d{3,4})\s?W', name, re.IGNORECASE)
    if wattage_match:
        attributes["wattage"] = int(wattage_match.group(1))

    # 80+ Rating
    if "80 plus" in name_lower or "80+" in name_lower:
        if "titanium" in name_lower: attributes["rating"] = "80+ Titanium"
        elif "platinum" in name_lower: attributes["rating"] = "80+ Platinum"
        elif "gold" in name_lower: attributes["rating"] = "80+ Gold"
        elif "silver" in name_lower: attributes["rating"] = "80+ Silver"
        elif "bronze" in name_lower: attributes["rating"] = "80+ Bronze"
        else: attributes["rating"] = "80+ White"

    # Modularity
    if "fully modular" in name_lower: attributes["modularity"] = "Fully Modular"
    elif "semi-modular" in name_lower or "semi modular" in name_lower: attributes["modularity"] = "Semi-Modular"
    elif "non-modular" in name_lower or "non modular" in name_lower: attributes["modularity"] = "Non-Modular"

    return attributes

def _parse_case(name: str) -> dict:
    """Parses attributes for a PC Case."""
    attributes = {}
    name_lower = name.lower()
    
    if "full tower" in name_lower: attributes["size"] = "Full Tower"
    elif "mid tower" in name_lower: attributes["size"] = "Mid Tower"
    elif "mini tower" in name_lower: attributes["size"] = "Mini Tower"
    elif "sff" in name_lower or "small form factor" in name_lower: attributes["size"] = "Small Form Factor"
    
    return attributes

def _parse_cooler(name: str) -> dict:
    """Parses attributes for a CPU Cooler."""
    attributes = {}
    name_lower = name.lower()

    if "liquid" in name_lower or "aio" in name_lower:
        attributes["type"] = "Liquid Cooler"
    elif "air cooler" in name_lower or "tower" in name_lower:
        attributes["type"] = "Air Cooler"
        
    return attributes


def parse_product_attributes(name: str, category_name: str) -> dict:
    """
    Top-level parser that routes to a category-specific parser.
    """
    category_name = category_name.lower()
    
    if "cpu" in category_name and "cooler" not in category_name: return _parse_cpu(name)
    if "graphics" in category_name: return _parse_gpu(name)
    if "monitor" in category_name: return _parse_monitor(name)
    if "motherboard" in category_name: return _parse_motherboard(name)
    if "memory" in category_name or "ram" in category_name: return _parse_ram(name)
    if "storage" in category_name or "ssd" in category_name or "hdd" in category_name: return _parse_storage(name)
    if "power supply" in category_name or "psu" in category_name: return _parse_psu(name)
    if "case" in category_name: return _parse_case(name)
    if "cooling" in category_name: return _parse_cooler(name)
        
    return {}

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
