import pandas as pd

# ==============================================================================
# 1. LOAD AND PREP THE TIME-SERIES DATA
# ==============================================================================
print("Loading proprietary compute history...\n")

try:
    # Read the continuous log, safely skipping any old or malformed rows
    df = pd.read_csv("proprietary_compute_index_feed.csv", on_bad_lines='skip')
    
    if df.empty:
        print("The data feed is currently empty. Waiting for the indexer to log more data.")
        exit()

    # Convert the raw text timestamp into a true datetime object
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # Set the timestamp as the dataframe index (required for time-series math)
    df.set_index('timestamp', inplace=True)

except FileNotFoundError:
    print("Error: 'proprietary_compute_index_feed.csv' not found. Please run the indexer first.")
    exit()
except Exception as e:
    print(f"An error occurred while loading the data: {e}")
    exit()

# ==============================================================================
# 2. CALCULATE DAILY MOVING AVERAGES (Smoothing out hourly noise)
# ==============================================================================
print("=== DAILY AVERAGE RENTAL RATES (FRONTIER VS STANDARD) ===")
print("Tracking the macro trend of compute pricing over time.\n")

try:
    # Group by hardware class, then resample into Daily ('D') buckets
    daily_avg = df.groupby('hardware_class').resample('D')['raw_gpu_hourly_rate'].mean().unstack(level=0)
    
    # Drop empty days and round for a clean financial output
    daily_avg = daily_avg.dropna().round(3)
    
    if not daily_avg.empty:
        print(daily_avg.to_string())
    else:
        print("Not enough historical data yet to calculate full daily averages.")
except Exception as e:
    print(f"Could not calculate daily averages: {e}")

print("\n" + "="*70 + "\n")

# ==============================================================================
# 3. INTRADAY VOLATILITY (Finding the cheapest hour of the day)
# ==============================================================================
print("=== INTRADAY PRICING: AVERAGE RATE BY HOUR OF DAY ===")
print("Use this to identify off-peak compute windows for batch processing.\n")

try:
    # Extract just the hour (0-23) from the index
    df['hour_of_day'] = df.index.hour

    # Group by the Hub and the Hour to find cyclical pricing floors
    hourly_cycle = df.groupby(['hub', 'hour_of_day'])['raw_gpu_hourly_rate'].mean().unstack(level=0)

    if not hourly_cycle.empty:
        print(hourly_cycle.round(3).to_string())
    else:
        print("Not enough data to map intraday cycles.")
except Exception as e:
    print(f"Could not calculate intraday cycles: {e}")