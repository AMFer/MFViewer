"""Test ignition angle channels."""

from mfviewer.data.parser import MFLogParser
from mfviewer.utils.units import UnitsManager
import numpy as np

log_file = r"C:\Users\gf006\Documents\Haltech\Nexus Maps and Data Logs\RCR 599 Prototipo\Logs\2025-12-21_1127am_Log272.csv"

parser = MFLogParser(log_file)
telemetry = parser.parse()
mgr = UnitsManager()

# Find ignition angle channels
angle_channels = [ch for ch in telemetry.channels if 'ignition' in ch.name.lower() and 'angle' in ch.name.lower()]

print("=" * 70)
print("IGNITION ANGLE CHANNELS")
print("=" * 70)

for ch in angle_channels[:5]:  # Check first 5
    data = telemetry.get_channel_data(ch.name)
    all_data = data.to_numpy()
    valid_data = all_data[~np.isnan(all_data)]

    if len(valid_data) > 0:
        print(f"\n{ch.name}:")
        print(f"  Type: {ch.data_type}")
        print(f"  Raw first 5: {valid_data[:5]}")
        print(f"  Raw mean: {valid_data.mean():.2f}")

        # Apply conversion
        converted = mgr.apply_channel_conversion(ch.name, valid_data[:100], ch.data_type)
        print(f"  Converted first 5: {converted[:5]}")
        print(f"  Converted mean: {converted.mean():.2f} degrees")

        # Check if has conversion
        has_forward = ch.name in mgr.channel_forward_conversions
        formula = mgr.channel_conversions.get(ch.name, 'None')
        print(f"  Haltech formula: {formula}")
        print(f"  Has conversion: {has_forward}")

        # Check if in expected range
        if 15 < converted.mean() < 20:
            print(f"  Status: OK (in expected range 15-20 degrees)")
        elif converted.mean() > 100:
            print(f"  Status: ERROR - too high, may need /10 conversion")
        elif converted.mean() < 5:
            print(f"  Status: ERROR - too low")
        else:
            print(f"  Status: Outside expected range (expected 15-20 degrees)")

print("\n" + "=" * 70)
print("Expected: Ignition timing around 15-20 degrees BTDC")
