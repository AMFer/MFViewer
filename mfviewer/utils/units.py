"""
Unit conversion and management for telemetry channels.
"""

import csv
import re
from pathlib import Path
from typing import Dict, Optional, Tuple, Callable
import numpy as np


class UnitsManager:
    """Manages unit information and conversions for telemetry channels."""

    def __init__(self):
        self.channel_units: Dict[str, str] = {}  # channel_name -> unit
        self.channel_conversions: Dict[str, str] = {}  # channel_name -> conversion formula
        self.channel_forward_conversions: Dict[str, Callable] = {}  # channel_name -> forward conversion function
        self.channel_inverse_conversions: Dict[str, Callable] = {}  # channel_name -> inverse conversion function
        self.unit_preferences: Dict[str, str] = {}  # unit_type -> preferred_unit
        self.cancel_haltech_conversion = False  # Whether to cancel out Haltech's conversion and show raw values

        # Map log file type names to standard unit names
        self.type_to_unit_map = {
            'Pressure': 'kPa',
            'AbsPressure': 'kPa (Abs)',
            'Temperature': 'K',
            'EngineSpeed': 'RPM',
            'Speed': 'km/h',
            'Percentage': '%',
            'Angle': '°',
            'BatteryVoltage': 'Volts',
            'AFR': 'λ',
            'Time_us': 'μs',
            'Time_ms': 'ms',
            'Raw': 'raw',
            # Add more mappings as needed
        }

        # Common unit conversions
        self.unit_conversions = {
            'K': {  # Temperature from Kelvin
                'K': lambda x: x,
                '°C': lambda x: x - 273.15,
                '°F': lambda x: (x - 273.15) * 9/5 + 32,
            },
            'kPa': {  # Pressure from kPa
                'kPa': lambda x: x,
                'psi': lambda x: x * 0.145038,
                'bar': lambda x: x * 0.01,
            },
            'kPa (Abs)': {  # Absolute pressure from kPa
                'kPa (Abs)': lambda x: x,
                'psi (Abs)': lambda x: x * 0.145038,
                'bar (Abs)': lambda x: x * 0.01,
            },
            'km/h': {  # Speed
                'km/h': lambda x: x,
                'mph': lambda x: x * 0.621371,
                'm/s': lambda x: x / 3.6,
            },
            'L': {  # Volume
                'L': lambda x: x,
                'gal': lambda x: x * 0.264172,
            },
            'cc': {  # Volume (small)
                'cc': lambda x: x,
                'mL': lambda x: x,
                'oz': lambda x: x * 0.033814,
            },
            'cc/min': {  # Flow rate
                'cc/min': lambda x: x,
                'L/hr': lambda x: x * 0.06,
                'gal/hr': lambda x: x * 0.0158503,
            },
            'λ': {  # AFR from Lambda
                'λ': lambda x: x,
                'AFR (Gas)': lambda x: x * 14.7,      # Gasoline stoichiometric ratio
                'AFR (E85)': lambda x: x * 9.765,     # E85 stoichiometric ratio
                'AFR (Methanol)': lambda x: x * 6.4,  # Methanol stoichiometric ratio
            },
        }

        # Default unit preferences
        self.default_preferences = {
            'K': '°C',  # Temperature in Celsius by default
            'kPa': 'psi',  # Pressure in psi
            'kPa (Abs)': 'psi (Abs)',  # Absolute pressure in psi
            'km/h': 'mph',  # Speed in mph
            'L': 'gal',  # Volume in gallons
            'cc': 'cc',  # Keep small volumes in cc
            'cc/min': 'L/hr',  # Flow rate in L/hr
            'λ': 'λ',  # Lambda by default (can change to AFR)
        }

        self.load_haltech_units()

    def _parse_haltech_forward_conversion(self, formula: str) -> Optional[Callable]:
        """
        Parse Haltech conversion formula and return forward function.

        The CSV files contain RAW sensor values, and the formula tells us
        how to convert them to display units.

        Examples:
            y = x/10 -> forward: x / 10
            y = x*10 -> forward: x * 10
            y = x/10 - 101.3 -> forward: x / 10 - 101.3

        Args:
            formula: Conversion formula string (e.g., "y = x/10")

        Returns:
            Forward conversion function or None if unable to parse
        """
        if not formula or 'y = x' not in formula.lower():
            return None

        try:
            # Extract the formula part after "y ="
            formula = formula.lower().replace(' ', '')
            match = re.search(r'y=(.+?)(?:\.|,|$)', formula)
            if not match:
                return None

            expr = match.group(1)

            # Check for subtraction offset
            offset = 0.0
            if '-' in expr and expr.count('-') == 1:
                parts = expr.split('-')
                expr = parts[0]
                try:
                    offset = -float(parts[1])  # Negative because we subtract
                except:
                    pass
            elif '+' in expr:
                parts = expr.split('+')
                expr = parts[0]
                try:
                    offset = float(parts[1])  # Positive because we add
                except:
                    pass

            # Remove 'x' from expression
            expr = expr.replace('x', '')

            # Parse multiplication/division
            multiplier = 1.0
            if expr.startswith('/'):
                # y = x/10 -> forward is x / 10
                try:
                    divisor = float(expr[1:])
                    multiplier = 1.0 / divisor
                except:
                    return None
            elif expr.startswith('*'):
                # y = x*10 -> forward is x * 10
                try:
                    mult = float(expr[1:])
                    multiplier = mult
                except:
                    return None
            elif '/' in expr and '*' in expr:
                # y = x*11/50 -> forward is x * 11 / 50
                try:
                    if expr.startswith('*'):
                        expr = expr[1:]
                    parts = expr.split('/')
                    num = float(parts[0])
                    denom = float(parts[1])
                    multiplier = num / denom
                except:
                    return None
            elif not expr:
                # y = x (no conversion)
                multiplier = 1.0
            else:
                return None

            # Create forward function
            # Forward: displayed = raw * multiplier + offset
            if offset != 0 and multiplier != 1.0:
                return lambda x, m=multiplier, o=offset: x * m + o if not np.isnan(x) else x
            elif multiplier != 1.0:
                return lambda x, m=multiplier: x * m if not np.isnan(x) else x
            elif offset != 0:
                return lambda x, o=offset: x + o if not np.isnan(x) else x
            else:
                return None  # No conversion needed

        except Exception as e:
            print(f"Error parsing forward conversion formula '{formula}': {e}")
            return None

    def _parse_haltech_conversion(self, formula: str) -> Optional[Callable]:
        """
        Parse Haltech conversion formula and return inverse function.

        Examples:
            y = x/10 -> inverse: x * 10
            y = x*10 -> inverse: x / 10
            y = x/10 - 101.3 -> inverse: (x + 101.3) * 10
            y = x*11/50 - 101.3 -> inverse: (x + 101.3) * 50/11

        Args:
            formula: Conversion formula string (e.g., "y = x/10")

        Returns:
            Inverse conversion function or None if unable to parse
        """
        if not formula or 'y = x' not in formula.lower():
            return None

        try:
            # Extract the formula part after "y ="
            formula = formula.lower().replace(' ', '')
            match = re.search(r'y=(.+?)(?:\.|,|$)', formula)
            if not match:
                return None

            expr = match.group(1)

            # Pattern: x/N or x*N or combinations with offset
            # y = x/10 - 101.3
            # y = x*10
            # y = x*11/50 - 101.3

            # Check for subtraction offset
            offset = 0.0
            if '-' in expr and expr.count('-') == 1:
                parts = expr.split('-')
                expr = parts[0]
                try:
                    offset = float(parts[1])
                except:
                    pass
            elif '+' in expr:
                parts = expr.split('+')
                expr = parts[0]
                try:
                    offset = -float(parts[1])  # Inverse: addition becomes subtraction
                except:
                    pass

            # Remove 'x' from expression
            expr = expr.replace('x', '')

            # Parse multiplication/division
            multiplier = 1.0
            if expr.startswith('/'):
                # y = x/10 -> inverse is x * 10
                try:
                    divisor = float(expr[1:])
                    multiplier = divisor
                except:
                    return None
            elif expr.startswith('*'):
                # y = x*10 -> inverse is x / 10
                try:
                    mult = float(expr[1:])
                    multiplier = 1.0 / mult
                except:
                    return None
            elif '/' in expr and '*' in expr:
                # y = x*11/50 -> inverse is x * 50/11
                try:
                    # Parse something like *11/50
                    if expr.startswith('*'):
                        expr = expr[1:]
                    parts = expr.split('/')
                    num = float(parts[0])
                    denom = float(parts[1])
                    # Inverse: multiply by denom/num
                    multiplier = denom / num
                except:
                    return None
            elif not expr:
                # y = x (no conversion)
                multiplier = 1.0
            else:
                return None

            # Create inverse function
            # The data files have already applied the forward conversion
            # Forward: displayed = raw * a - b  (where a=1/divisor for x/10, or a=mult for x*10)
            # We need inverse to get back to raw: raw = (displayed + b) / a
            #
            # Example: y = x/10 - 101.3
            #   displayed = raw/10 - 101.3
            #   raw = (displayed + 101.3) * 10
            #
            # In our case:
            # - For y = x/10: multiplier = 10 (we multiply to invert the division)
            # - For y = x*10: multiplier = 1/10 (we divide to invert the multiplication)

            if offset != 0 and multiplier != 1.0:
                return lambda x, m=multiplier, o=offset: (x + o) * m if not np.isnan(x) else x
            elif multiplier != 1.0:
                return lambda x, m=multiplier: x * m if not np.isnan(x) else x
            else:
                return None  # No conversion needed

        except Exception as e:
            print(f"Error parsing conversion formula '{formula}': {e}")
            return None

    def load_haltech_units(self):
        """Load unit information from Haltech CSV file."""
        csv_path = Path(__file__).parent.parent.parent / 'Assets' / 'Haltech Units Only.csv'

        if not csv_path.exists():
            print(f"Warning: Haltech units file not found at {csv_path}")
            return

        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    channel = row.get('Channel', '').strip()
                    units = row.get('Units', '').strip()
                    conversion = row.get('Conversion from Raw', '').strip()

                    if channel and channel != '-':
                        self.channel_units[channel] = units
                        if conversion:
                            self.channel_conversions[channel] = conversion
                            # Parse and store FORWARD conversion (raw -> display)
                            forward_func = self._parse_haltech_forward_conversion(conversion)
                            if forward_func:
                                self.channel_forward_conversions[channel] = forward_func
                            # Parse and store inverse conversion (display -> raw)
                            inverse_func = self._parse_haltech_conversion(conversion)
                            if inverse_func:
                                self.channel_inverse_conversions[channel] = inverse_func

            # Add channel name aliases for common variations
            self._add_channel_aliases()
        except Exception as e:
            print(f"Error loading Haltech units: {e}")

    def _add_channel_aliases(self):
        """Add aliases for channels that may have different names in log files."""
        aliases = {
            # Wideband sensors: "Wideband Sensor X" -> "Wideband O2 X"
            'Wideband Sensor 1': ['Wideband O2 1'],
            'Wideband Sensor 2': ['Wideband O2 2'],
            'Wideband Bank 1': ['Wideband O2 Bank 1'],
            'Wideband Bank 2': ['Wideband O2 Bank 2'],
            'Wideband Overall': ['Wideband O2 Overall'],
        }

        for original_name, alias_list in aliases.items():
            if original_name in self.channel_forward_conversions:
                # Copy conversion data to alias names
                for alias in alias_list:
                    self.channel_units[alias] = self.channel_units.get(original_name)
                    self.channel_conversions[alias] = self.channel_conversions.get(original_name)
                    self.channel_forward_conversions[alias] = self.channel_forward_conversions.get(original_name)
                    if original_name in self.channel_inverse_conversions:
                        self.channel_inverse_conversions[alias] = self.channel_inverse_conversions.get(original_name)

    def get_unit(self, channel_name: str, use_preference: bool = True, channel_type: str = None) -> str:
        """
        Get the unit for a channel.

        Args:
            channel_name: Name of the channel
            use_preference: Whether to use user's preferred unit
            channel_type: Type from log file header (e.g., 'Pressure', 'Temperature')

        Returns:
            Unit string
        """
        # Use channel_type from log file if provided, otherwise fall back to Haltech CSV
        if channel_type:
            base_unit = self.type_to_unit_map.get(channel_type, channel_type)
        else:
            base_unit = self.channel_units.get(channel_name, '')

        if not use_preference or not base_unit:
            return base_unit

        # Check if user has a preference for this unit type
        preferred = self.unit_preferences.get(base_unit)
        if preferred:
            return preferred

        # Use default preference if available
        return self.default_preferences.get(base_unit, base_unit)

    def get_base_unit(self, channel_name: str) -> str:
        """Get the base unit from Haltech data (unconverted)."""
        return self.channel_units.get(channel_name, '')

    def convert_value(self, value: float, from_unit: str, to_unit: str) -> float:
        """
        Convert a value from one unit to another.

        Args:
            value: Value to convert
            from_unit: Source unit
            to_unit: Target unit

        Returns:
            Converted value
        """
        if from_unit == to_unit or not from_unit or not to_unit:
            return value

        # Get conversion functions for this unit type
        conversions = self.unit_conversions.get(from_unit)
        if not conversions:
            return value  # No conversion available

        converter = conversions.get(to_unit)
        if not converter:
            return value  # No conversion to target unit

        return converter(value)

    def convert_array(self, values: np.ndarray, from_unit: str, to_unit: str) -> np.ndarray:
        """
        Convert an array of values from one unit to another.

        Args:
            values: Array of values to convert
            from_unit: Source unit
            to_unit: Target unit

        Returns:
            Converted array
        """
        if from_unit == to_unit or not from_unit or not to_unit:
            return values

        conversions = self.unit_conversions.get(from_unit)
        if not conversions:
            return values

        converter = conversions.get(to_unit)
        if not converter:
            return values

        # Apply conversion to entire array
        return np.array([converter(v) if not np.isnan(v) else v for v in values])

    def set_unit_preference(self, base_unit: str, preferred_unit: str):
        """
        Set user's preferred unit for a base unit type.

        Args:
            base_unit: The base unit type (e.g., 'K', 'kPa')
            preferred_unit: The preferred unit (e.g., '°C', 'psi')
        """
        self.unit_preferences[base_unit] = preferred_unit

    def get_available_units(self, base_unit: str) -> list:
        """
        Get list of available unit conversions for a base unit.

        Args:
            base_unit: The base unit type

        Returns:
            List of available units
        """
        if base_unit in self.unit_conversions:
            return list(self.unit_conversions[base_unit].keys())
        return [base_unit] if base_unit else []

    def get_all_base_units(self) -> list:
        """Get all base unit types that have conversions available."""
        return list(self.unit_conversions.keys())

    def get_preferences(self) -> Dict[str, str]:
        """Get current unit preferences."""
        # Merge default preferences with user preferences
        prefs = self.default_preferences.copy()
        prefs.update(self.unit_preferences)
        return prefs

    def set_preferences(self, preferences: Dict[str, str]):
        """Set unit preferences from a dictionary."""
        self.unit_preferences = preferences.copy()

    def apply_channel_conversion(self, channel_name: str, values: np.ndarray, channel_type: str = None) -> np.ndarray:
        """
        Apply conversion to channel data.

        The CSV files contain RAW sensor values. By default, we:
        1. Apply the FORWARD Haltech conversion (raw -> kPa/°C/etc)
        2. Apply user's unit preference (kPa -> PSI, etc)

        If cancel_haltech_conversion is True, we skip step 1 and show raw values.

        Args:
            channel_name: Name of the channel
            values: Array of RAW values from the CSV file
            channel_type: Unit type from the log file header (e.g., 'Pressure', 'Temperature', 'EngineSpeed')

        Returns:
            Converted array
        """
        # Map channel_type from log file to base unit (e.g., 'Pressure' -> 'kPa')
        if channel_type:
            base_unit = self.type_to_unit_map.get(channel_type, channel_type)
        else:
            base_unit = self.get_base_unit(channel_name)

        if self.cancel_haltech_conversion:
            # User wants raw values - skip Haltech conversion, just apply unit preference
            preferred_unit = self.unit_preferences.get(base_unit, self.default_preferences.get(base_unit, base_unit))
            return self.convert_array(values, base_unit, preferred_unit)

        # Normal mode: Apply FORWARD Haltech conversion first (raw -> base unit)
        if channel_name in self.channel_forward_conversions:
            forward_func = self.channel_forward_conversions[channel_name]
            values = np.array([forward_func(v) for v in values])

        # Then apply unit preference conversion from base unit to preferred unit
        preferred_unit = self.unit_preferences.get(base_unit, self.default_preferences.get(base_unit, base_unit))
        return self.convert_array(values, base_unit, preferred_unit)

    def get_conversion_info(self, channel_name: str) -> str:
        """
        Get human-readable conversion information for a channel.

        Args:
            channel_name: Name of the channel

        Returns:
            Description of the conversion applied
        """
        info_parts = []

        # Haltech conversion
        if channel_name in self.channel_conversions:
            haltech_formula = self.channel_conversions[channel_name]
            info_parts.append(f"Haltech: {haltech_formula}")

        # Current unit preference
        base_unit = self.get_base_unit(channel_name)
        preferred_unit = self.get_unit(channel_name, use_preference=True)
        if base_unit and preferred_unit and base_unit != preferred_unit:
            info_parts.append(f"Display: {base_unit} → {preferred_unit}")

        return " | ".join(info_parts) if info_parts else "No conversion"
