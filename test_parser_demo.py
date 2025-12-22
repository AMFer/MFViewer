"""
Quick test script to validate the MF log parser.
"""

from mfviewer.data.parser import MFLogParser

# Path to example log file
log_file = r"C:\Users\gf006\Documents\Telemetry\Logs\2025-12-21_1127am_Log272.csv"

print("Parsing telemetry log file...")
print(f"File: {log_file}\n")

# Parse the file
parser = MFLogParser(log_file)
telemetry = parser.parse()

# Display results
print(telemetry)
print(f"\nMetadata:")
for key, value in telemetry.metadata.items():
    print(f"  {key}: {value}")

print(f"\nTotal channels: {len(telemetry.channels)}")
print(f"\nFirst 10 channels:")
for i, ch in enumerate(telemetry.channels[:10], 1):
    print(f"  {i}. {ch.name} (ID: {ch.channel_id}, Type: {ch.data_type}, Range: {ch.min_value}-{ch.max_value})")

print(f"\nData shape: {telemetry.data.shape}")
print(f"Time range: {telemetry.get_time_range()[0]:.3f}s to {telemetry.get_time_range()[1]:.3f}s")
print(f"Duration: {telemetry.get_time_range()[1] - telemetry.get_time_range()[0]:.3f}s")

# Show some sample data
print(f"\nFirst 5 data rows:")
print(telemetry.data.head())

# Show statistics for a channel (if available)
if telemetry.channels:
    sample_channel = telemetry.channels[0].name
    stats = telemetry.get_statistics(sample_channel)
    if stats:
        print(f"\nStatistics for '{sample_channel}':")
        for key, value in stats.items():
            print(f"  {key}: {value}")
