import os
import requests
import pandas as pd

# ==============================================================================
# 1. CONFIGURATION & BENCHMARKS
# ==============================================================================
# Hardware Asset Classification Matrix
FRONTIER_MODELS = ["B200", "B300", "H200"]
STANDARD_MODELS = ["H100", "A100", "4090", "A6000", "V100"]

DATACENTER_PUE = 1.3  # Infrastructure cooling overhead multiplier

# Global Hub Constants (Estimated Industrial Electricity rates per kWh in USD)
# These act as the basis for calculating the local energy margin floor
REGIONAL_POWER_RATES = {
    "US-VA": 0.08,   # Northern Virginia (Ashburn cluster)
    "US-TX": 0.06,   # Texas (ERCOT grid)
    "US-OTHER": 0.11,
    "UK": 0.28,      # United Kingdom 
    "EU": 0.20,      # Continental Europe Average
    "ASIA": 0.15,    # APAC Trading Hubs (Japan, Singapore, Korea)
    "OTHER": 0.12    # Global Fallback Baseline
}

def get_regional_power_rate(hub_code):
    return REGIONAL_POWER_RATES.get(hub_code, REGIONAL_POWER_RATES["OTHER"])

# ==============================================================================
# 2. INGESTION & GLOBAL GEOLOCATION
# ==============================================================================
def fetch_raw_compute_data():
    print("Fetching open marketplace data...")
    url = "https://console.vast.ai/api/v0/bundles/"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        all_offers = response.json().get('offers', [])
        print(f"Downloaded {len(all_offers)} total raw market records successfully.")
        return all_offers
    except Exception as e:
        print(f"Error fetching data: {e}")
        return []

def resolve_geographic_hub(offer):
    # Extract metadata strings to parse out international jurisdiction codes
    geo_info = str(offer.get('geolocation', '') or '').upper()
    location_info = str(offer.get('location', '') or '').upper()
    combined_geo = geo_info + " " + location_info
    
    # North American Trading Hubs
    if "VA" in combined_geo or "VIRGINIA" in combined_geo:
        return "US-VA"
    elif "TX" in combined_geo or "TEXAS" in combined_geo:
        return "US-TX"
    elif "US" in combined_geo or "UNITED STATES" in combined_geo or "CA " in combined_geo:
        return "US-OTHER"
        
    # Europe & United Kingdom
    elif any(code in combined_geo for code in ["GB", "UK", "UNITED KINGDOM", "LONDON"]):
        return "UK"
    elif any(code in combined_geo for code in ["FR", "DE", "IT", "ES", "NL", "FI", "NO", "SE", "CH", "EU", "FRANKFURT"]):
        return "EU"
        
    # Asia-Pacific
    elif any(code in combined_geo for code in ["JP", "KR", "SG", "TW", "IN", "HK", "TOKYO", "SEOUL", "SINGAPORE"]):
        return "ASIA"
        
    return "OTHER"

# ==============================================================================
# 3. PROPRIETARY CALCULATIONS & NORMALIZATION
# ==============================================================================
def process_compute_metrics(offers):
    processed_records = []
    
    for offer in offers:
        if not offer.get('rentable', False):
            continue
            
        gpu_name = str(offer.get('gpu_name', '')).upper()
        
        # Determine Tiers and map structural physics properties
        hardware_class = "UNKNOWN"
        if any(target in gpu_name for target in FRONTIER_MODELS):
            hardware_class = "FRONTIER"
            throughput_tps = 6000  # High efficiency/Next-Gen output capacity
            system_tdp_kw = 1.0    # Increased power draw per node
        elif any(target in gpu_name for target in STANDARD_MODELS):
            hardware_class = "STANDARD"
            throughput_tps = 3000  # Standard workhorse capacity
            system_tdp_kw = 0.7    # Legacy baseline power draw
        else:
            continue # Filter out non-enterprise or highly illiquid consumer nodes
            
        raw_hourly_rate = float(offer.get('dph_base', 0))
        if raw_hourly_rate <= 0:
            continue
            
        num_gpus = int(offer.get('num_gpus', 1))
        unit_gpu_hourly_rate = raw_hourly_rate / num_gpus
        
        # 1. Map Geolocation Hub
        hub = resolve_geographic_hub(offer)
        
        # 2. Extract Energy Mechanics
        power_rate = get_regional_power_rate(hub)
        total_system_draw_kw = system_tdp_kw * DATACENTER_PUE
        hourly_electricity_cost = total_system_draw_kw * power_rate
        implied_hardware_margin = unit_gpu_hourly_rate - hourly_electricity_cost
        
        # 3. Calculate Token Economics
        hourly_token_throughput = throughput_tps * 3600
        cost_per_million_tokens = (unit_gpu_hourly_rate / hourly_token_throughput) * 1_000_000
        
        record = {
            "machine_id": offer.get('id'),
            "gpu_model": offer.get('gpu_name'),
            "hardware_class": hardware_class,
            "hub": hub,
            "gpu_count": num_gpus,
            "raw_gpu_hourly_rate": round(unit_gpu_hourly_rate, 3),
            "hourly_electricity_cost": round(hourly_electricity_cost, 4),
            "implied_hardware_margin": round(implied_hardware_margin, 4),
            "cost_per_million_tokens": round(cost_per_million_tokens, 4)
        }
        processed_records.append(record)
        
    return pd.DataFrame(processed_records)

# ==============================================================================
# 4. EXECUTING & LOGGING THE TIME-SERIES SNAPSHOT
# ==============================================================================
if __name__ == "__main__":
    raw_offers = fetch_raw_compute_data()
    
    if not raw_offers:
        print("No connection to marketplace. Exiting.")
    else:
        df = process_compute_metrics(raw_offers)
        
        if df.empty:
            print("No matching target GPUs found in current live sample.")
        else:
            print(f"Successfully processed {len(df)} production nodes.\n")
            
            # Print the structured Multi-Index Summary table to console
            print("=== PROPRIETARY COMPUTE INDEX SUMMARY ===")
            summary = df.groupby(['hub', 'hardware_class']).agg(
                avg_gpu_rate=('raw_gpu_hourly_rate', 'mean'),
                avg_power_cost=('hourly_electricity_cost', 'mean'),
                avg_hw_margin=('implied_hardware_margin', 'mean'),
                token_price_m=('cost_per_million_tokens', 'mean'),
                active_nodes=('machine_id', 'count')
            ).round(3)
            print(summary.to_string())
            
            # Timestamp the dataset to log historical data changes over time
            df['timestamp'] = pd.to_datetime('now')
            
            # Set target file path for execution output
            csv_file = "proprietary_compute_index_feed.csv"
            file_exists = os.path.isfile(csv_file)
            
            # Append data row block seamlessly without clearing older historic runs
            df.to_csv(csv_file, mode='a', index=False, header=not file_exists)
            print(f"\nSuccessfully appended snapshot tick to '{csv_file}'")