"""
Dyno Pull Analyzer - Analysis engine for WOT dyno pull analysis.

Provides automatic detection of WOT (Wide Open Throttle) regions and
analysis of key metrics including AFR, knock, oil/fuel pressure, and timing.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
import numpy as np


# Channel name patterns for auto-detection
CHANNEL_PATTERNS = {
    'rpm': ['Engine Speed', 'RPM', 'Engine RPM', 'Engine Speed (RPM)'],
    'tps': ['Throttle Position', 'TPS', 'Throttle', 'Throttle Position (Main)'],
    'afr': ['Wideband O2 Overall', 'Wideband O2 1', 'Lambda 1', 'AFR',
            'Wideband Overall', 'O2 Wideband', 'Air Fuel Ratio'],
    'lambda': ['Lambda', 'Lambda 1', 'Wideband Lambda'],
    'knock_count': ['Knock Count', 'Knock Count Cyl', 'Total Knock Count'],
    'knock_level': ['Knock Level', 'Knock Intensity', 'Knock Signal'],
    'knock_retard': ['Knock Retard', 'Knock Timing Retard', 'KR'],
    'oil_pressure': ['Oil Pressure', 'Engine Oil Pressure', 'Oil Press'],
    'fuel_pressure': ['Fuel Pressure', 'Rail Pressure', 'Fuel Rail Pressure',
                      'Fuel Pressure (Gauge)'],
    'timing': ['Ignition Angle', 'Spark Advance', 'Timing', 'Ignition Timing',
               'Spark Timing', 'Timing Advance'],
}


@dataclass
class AFRAnalysis:
    """Analysis results for Air/Fuel Ratio."""
    average: float = 0.0
    minimum: float = 0.0
    maximum: float = 0.0
    target: float = 12.5
    too_lean_count: int = 0  # Samples above lean threshold
    too_rich_count: int = 0  # Samples below rich threshold
    status: str = 'pass'  # 'pass', 'warn', 'fail'
    message: str = ''

    # Per-RPM bin data
    rpm_bins: List[float] = field(default_factory=list)
    bin_averages: List[float] = field(default_factory=list)
    bin_statuses: List[str] = field(default_factory=list)


@dataclass
class KnockAnalysis:
    """Analysis results for knock detection."""
    total_events: int = 0
    max_retard: float = 0.0
    knock_rpm_ranges: List[Tuple[float, float]] = field(default_factory=list)
    status: str = 'pass'
    message: str = ''

    # Per-RPM bin data
    rpm_bins: List[float] = field(default_factory=list)
    bin_counts: List[int] = field(default_factory=list)
    bin_max_retard: List[float] = field(default_factory=list)
    bin_statuses: List[str] = field(default_factory=list)


@dataclass
class PressureAnalysis:
    """Analysis results for pressure (oil or fuel)."""
    pressure_type: str = 'oil'  # 'oil' or 'fuel'
    average: float = 0.0
    minimum: float = 0.0
    maximum: float = 0.0
    drop_percent: float = 0.0  # Max drop from peak
    min_threshold: float = 25.0  # psi
    status: str = 'pass'
    message: str = ''

    # Per-RPM bin data
    rpm_bins: List[float] = field(default_factory=list)
    bin_averages: List[float] = field(default_factory=list)
    bin_statuses: List[str] = field(default_factory=list)


@dataclass
class TimingAnalysis:
    """Analysis results for ignition timing."""
    average: float = 0.0
    minimum: float = 0.0
    maximum: float = 0.0
    retard_events: int = 0  # Significant timing drops
    status: str = 'pass'
    message: str = ''

    # Per-RPM bin data
    rpm_bins: List[float] = field(default_factory=list)
    bin_averages: List[float] = field(default_factory=list)
    bin_statuses: List[str] = field(default_factory=list)


@dataclass
class RPMBinData:
    """Data for a single RPM bin row in the detail table."""
    rpm: float
    afr: Optional[float] = None
    knock_count: int = 0
    oil_psi: Optional[float] = None
    fuel_psi: Optional[float] = None
    timing_deg: Optional[float] = None
    status: str = 'pass'  # Row status for coloring


@dataclass
class DynoPullResult:
    """Complete analysis results for a dyno pull."""
    duration: float = 0.0
    start_time: float = 0.0
    end_time: float = 0.0
    rpm_min: float = 0.0
    rpm_max: float = 0.0
    peak_tps: float = 0.0

    afr: AFRAnalysis = field(default_factory=AFRAnalysis)
    knock: KnockAnalysis = field(default_factory=KnockAnalysis)
    oil_pressure: PressureAnalysis = field(default_factory=lambda: PressureAnalysis(pressure_type='oil'))
    fuel_pressure: PressureAnalysis = field(default_factory=lambda: PressureAnalysis(pressure_type='fuel'))
    timing: TimingAnalysis = field(default_factory=TimingAnalysis)

    # Combined RPM bin table data
    rpm_bin_data: List[RPMBinData] = field(default_factory=list)

    overall_status: str = 'pass'  # 'pass', 'warn', 'fail'

    def calculate_overall_status(self):
        """Calculate overall status from individual analyses."""
        statuses = [
            self.afr.status,
            self.knock.status,
            self.oil_pressure.status,
            self.fuel_pressure.status,
            self.timing.status,
        ]
        if 'fail' in statuses:
            self.overall_status = 'fail'
        elif 'warn' in statuses:
            self.overall_status = 'warn'
        else:
            self.overall_status = 'pass'


class DynoPullAnalyzer:
    """
    Analyzes WOT dyno pulls from telemetry data.

    Provides automatic WOT region detection and analysis of:
    - AFR/Lambda
    - Knock events
    - Oil pressure
    - Fuel pressure
    - Ignition timing
    """

    def __init__(self, telemetry_data, units_manager=None):
        """
        Initialize analyzer with telemetry data.

        Args:
            telemetry_data: TelemetryData object with parsed log data
            units_manager: Optional UnitsManager for unit conversions
        """
        self.telemetry = telemetry_data
        self.units_manager = units_manager

        # Analysis settings (defaults)
        self.settings = {
            'tps_threshold': 95.0,  # % for WOT detection
            'afr_target': 12.5,  # AFR target for NA
            'afr_lean_threshold': 13.5,  # Above this = too lean
            'afr_rich_threshold': 11.5,  # Below this = too rich
            'oil_min_psi': 25.0,  # Minimum oil pressure
            'oil_drop_warn_percent': 15.0,  # Warn if drop > this %
            'fuel_drop_warn_percent': 10.0,  # Warn if drop > this %
            'rpm_bin_size': 500,  # RPM bin width
            'knock_retard_threshold': 1.0,  # Degrees retard to flag
        }

        # Channel mappings (auto-detected or user-specified)
        self.channel_map = {}

    def update_settings(self, **kwargs):
        """Update analysis settings."""
        self.settings.update(kwargs)

    def set_channel(self, channel_type: str, channel_name: str):
        """Set channel mapping for a specific type."""
        self.channel_map[channel_type] = channel_name

    def auto_detect_channels(self, available_channels: List[str]) -> Dict[str, Optional[str]]:
        """
        Auto-detect channel mappings from available channels.

        Args:
            available_channels: List of channel names in the telemetry data

        Returns:
            Dict mapping channel types to detected channel names (or None)
        """
        detected = {}
        available_lower = {ch.lower(): ch for ch in available_channels}

        for channel_type, patterns in CHANNEL_PATTERNS.items():
            detected[channel_type] = None
            for pattern in patterns:
                pattern_lower = pattern.lower()
                # Exact match first
                if pattern_lower in available_lower:
                    detected[channel_type] = available_lower[pattern_lower]
                    break
                # Partial match
                for avail_lower, avail_orig in available_lower.items():
                    if pattern_lower in avail_lower:
                        detected[channel_type] = avail_orig
                        break
                if detected[channel_type]:
                    break

        # Store detected channels
        self.channel_map.update({k: v for k, v in detected.items() if v})
        return detected

    def get_channel_data(self, channel_type: str) -> Optional[np.ndarray]:
        """Get data array for a channel type."""
        channel_name = self.channel_map.get(channel_type)
        if not channel_name or not self.telemetry:
            return None

        series = self.telemetry.get_channel_data(channel_name)
        if series is not None:
            return series.values.astype(np.float64)
        return None

    def get_time_data(self) -> Optional[np.ndarray]:
        """Get time array from telemetry (Seconds index)."""
        if not self.telemetry or self.telemetry.data is None:
            return None
        # Time is stored in the DataFrame index
        return self.telemetry.data.index.values.astype(np.float64)

    def find_wot_regions(self,
                         tps_threshold: Optional[float] = None,
                         time_range: Optional[Tuple[float, float]] = None
                         ) -> List[Tuple[float, float]]:
        """
        Find time regions where TPS >= threshold.

        Args:
            tps_threshold: TPS threshold percentage (default from settings)
            time_range: Optional (start, end) time range to search within

        Returns:
            List of (start_time, end_time) tuples for regions over threshold
        """
        if tps_threshold is None:
            tps_threshold = self.settings['tps_threshold']

        time_data = self.get_time_data()
        tps_data = self.get_channel_data('tps')

        if time_data is None or tps_data is None:
            return []

        # Apply time range filter if specified
        if time_range:
            mask = (time_data >= time_range[0]) & (time_data <= time_range[1])
            time_data = time_data[mask]
            tps_data = tps_data[mask]

        if len(time_data) == 0:
            return []

        # Find samples over threshold
        wot_mask = tps_data >= tps_threshold

        # Find contiguous regions
        regions = []
        in_region = False
        region_start = 0.0

        for i, is_wot in enumerate(wot_mask):
            if is_wot and not in_region:
                # Start of new region
                in_region = True
                region_start = time_data[i]
            elif not is_wot and in_region:
                # End of region
                in_region = False
                region_end = time_data[i - 1]
                regions.append((region_start, region_end))

        # Handle region that extends to end
        if in_region:
            region_end = time_data[-1]
            regions.append((region_start, region_end))

        return regions

    def analyze_pull(self,
                     start_time: float,
                     end_time: float) -> DynoPullResult:
        """
        Analyze a single WOT pull.

        Args:
            start_time: Pull start time
            end_time: Pull end time

        Returns:
            DynoPullResult with complete analysis
        """
        result = DynoPullResult(
            start_time=start_time,
            end_time=end_time,
            duration=end_time - start_time,
        )

        time_data = self.get_time_data()
        if time_data is None:
            return result

        # Get time mask for this pull
        time_mask = (time_data >= start_time) & (time_data <= end_time)

        # Get RPM data for binning
        rpm_data = self.get_channel_data('rpm')
        if rpm_data is not None:
            rpm_in_pull = rpm_data[time_mask]
            if len(rpm_in_pull) > 0:
                result.rpm_min = float(np.min(rpm_in_pull))
                result.rpm_max = float(np.max(rpm_in_pull))

        # Get peak TPS
        tps_data = self.get_channel_data('tps')
        if tps_data is not None:
            tps_in_pull = tps_data[time_mask]
            if len(tps_in_pull) > 0:
                result.peak_tps = float(np.max(tps_in_pull))

        # Generate RPM bins
        rpm_bin_size = self.settings['rpm_bin_size']
        if result.rpm_max > result.rpm_min:
            bin_start = int(result.rpm_min // rpm_bin_size) * rpm_bin_size
            bin_end = int(result.rpm_max // rpm_bin_size + 1) * rpm_bin_size
            rpm_bins = list(range(bin_start, bin_end + 1, rpm_bin_size))
        else:
            rpm_bins = []

        # Run individual analyses
        result.afr = self._analyze_afr(time_mask, rpm_data, rpm_bins)
        result.knock = self._analyze_knock(time_mask, rpm_data, rpm_bins)
        result.oil_pressure = self._analyze_pressure(time_mask, rpm_data, rpm_bins, 'oil')
        result.fuel_pressure = self._analyze_pressure(time_mask, rpm_data, rpm_bins, 'fuel')
        result.timing = self._analyze_timing(time_mask, rpm_data, rpm_bins)

        # Build combined RPM bin table
        result.rpm_bin_data = self._build_rpm_bin_table(result, rpm_bins)

        # Calculate overall status
        result.calculate_overall_status()

        return result

    def _analyze_afr(self,
                     time_mask: np.ndarray,
                     rpm_data: Optional[np.ndarray],
                     rpm_bins: List[int]) -> AFRAnalysis:
        """Analyze AFR/Lambda data."""
        analysis = AFRAnalysis(target=self.settings['afr_target'])

        # Try AFR channel first, then Lambda
        afr_data = self.get_channel_data('afr')
        is_lambda = False

        if afr_data is None:
            afr_data = self.get_channel_data('lambda')
            is_lambda = True

        if afr_data is None:
            analysis.message = 'No AFR/Lambda channel found'
            return analysis

        afr_in_pull = afr_data[time_mask]
        if len(afr_in_pull) == 0:
            return analysis

        # Convert Lambda to AFR if needed (stoich = 14.7 for gasoline)
        if is_lambda:
            afr_in_pull = afr_in_pull * 14.7

        # Overall stats
        analysis.average = float(np.mean(afr_in_pull))
        analysis.minimum = float(np.min(afr_in_pull))
        analysis.maximum = float(np.max(afr_in_pull))

        # Count lean/rich samples
        lean_threshold = self.settings['afr_lean_threshold']
        rich_threshold = self.settings['afr_rich_threshold']
        analysis.too_lean_count = int(np.sum(afr_in_pull > lean_threshold))
        analysis.too_rich_count = int(np.sum(afr_in_pull < rich_threshold))

        # Determine status
        if analysis.too_lean_count > len(afr_in_pull) * 0.1:  # >10% too lean
            analysis.status = 'fail'
            analysis.message = f'Too lean: {analysis.too_lean_count} samples above {lean_threshold}:1'
        elif analysis.too_rich_count > len(afr_in_pull) * 0.2:  # >20% too rich
            analysis.status = 'warn'
            analysis.message = f'Running rich: {analysis.too_rich_count} samples below {rich_threshold}:1'
        elif analysis.too_lean_count > 0:
            analysis.status = 'warn'
            analysis.message = f'Some lean spots detected'
        else:
            analysis.status = 'pass'
            analysis.message = f'AFR in safe range'

        # Per-RPM bin analysis
        if rpm_data is not None and len(rpm_bins) > 1:
            rpm_in_pull = rpm_data[time_mask]
            analysis.rpm_bins = [(rpm_bins[i] + rpm_bins[i+1]) / 2 for i in range(len(rpm_bins)-1)]

            for i in range(len(rpm_bins) - 1):
                bin_mask = (rpm_in_pull >= rpm_bins[i]) & (rpm_in_pull < rpm_bins[i+1])
                bin_afr = afr_in_pull[bin_mask]

                if len(bin_afr) > 0:
                    bin_avg = float(np.mean(bin_afr))
                    analysis.bin_averages.append(bin_avg)

                    if bin_avg > lean_threshold:
                        analysis.bin_statuses.append('fail')
                    elif bin_avg < rich_threshold:
                        analysis.bin_statuses.append('warn')
                    elif bin_avg > self.settings['afr_target'] + 0.5:
                        analysis.bin_statuses.append('warn')
                    else:
                        analysis.bin_statuses.append('pass')
                else:
                    analysis.bin_averages.append(None)
                    analysis.bin_statuses.append('none')

        return analysis

    def _analyze_knock(self,
                       time_mask: np.ndarray,
                       rpm_data: Optional[np.ndarray],
                       rpm_bins: List[int]) -> KnockAnalysis:
        """Analyze knock events."""
        analysis = KnockAnalysis()

        # Try different knock channels
        knock_count = self.get_channel_data('knock_count')
        knock_retard = self.get_channel_data('knock_retard')
        knock_level = self.get_channel_data('knock_level')

        has_knock_data = False

        # Analyze knock count if available
        if knock_count is not None:
            has_knock_data = True
            count_in_pull = knock_count[time_mask]
            if len(count_in_pull) > 0:
                # Knock count is cumulative - look for increases
                if len(count_in_pull) > 1:
                    count_diff = np.diff(count_in_pull)
                    analysis.total_events = int(np.sum(count_diff > 0))

        # Analyze knock retard if available
        if knock_retard is not None:
            has_knock_data = True
            retard_in_pull = knock_retard[time_mask]
            if len(retard_in_pull) > 0:
                analysis.max_retard = float(np.max(np.abs(retard_in_pull)))

        if not has_knock_data:
            analysis.message = 'No knock channels found'
            return analysis

        # Determine status
        threshold = self.settings['knock_retard_threshold']
        if analysis.total_events > 5 or analysis.max_retard > 3.0:
            analysis.status = 'fail'
            analysis.message = f'{analysis.total_events} knock events, {analysis.max_retard:.1f}° max retard'
        elif analysis.total_events > 0 or analysis.max_retard > threshold:
            analysis.status = 'warn'
            analysis.message = f'{analysis.total_events} knock events detected'
        else:
            analysis.status = 'pass'
            analysis.message = 'No knock detected'

        # Per-RPM bin analysis
        if rpm_data is not None and len(rpm_bins) > 1:
            rpm_in_pull = rpm_data[time_mask]
            analysis.rpm_bins = [(rpm_bins[i] + rpm_bins[i+1]) / 2 for i in range(len(rpm_bins)-1)]

            for i in range(len(rpm_bins) - 1):
                bin_mask = (rpm_in_pull >= rpm_bins[i]) & (rpm_in_pull < rpm_bins[i+1])

                # Count in this bin
                bin_count = 0
                if knock_count is not None:
                    bin_knock = knock_count[time_mask][bin_mask]
                    if len(bin_knock) > 1:
                        bin_count = int(np.sum(np.diff(bin_knock) > 0))

                analysis.bin_counts.append(bin_count)

                # Max retard in this bin
                bin_max = 0.0
                if knock_retard is not None:
                    bin_retard = knock_retard[time_mask][bin_mask]
                    if len(bin_retard) > 0:
                        bin_max = float(np.max(np.abs(bin_retard)))

                analysis.bin_max_retard.append(bin_max)

                # Status
                if bin_count > 2 or bin_max > 3.0:
                    analysis.bin_statuses.append('fail')
                elif bin_count > 0 or bin_max > threshold:
                    analysis.bin_statuses.append('warn')
                else:
                    analysis.bin_statuses.append('pass')

        return analysis

    def _analyze_pressure(self,
                          time_mask: np.ndarray,
                          rpm_data: Optional[np.ndarray],
                          rpm_bins: List[int],
                          pressure_type: str) -> PressureAnalysis:
        """Analyze oil or fuel pressure."""
        analysis = PressureAnalysis(pressure_type=pressure_type)

        if pressure_type == 'oil':
            pressure_data = self.get_channel_data('oil_pressure')
            min_threshold = self.settings['oil_min_psi']
            drop_warn = self.settings['oil_drop_warn_percent']
        else:
            pressure_data = self.get_channel_data('fuel_pressure')
            min_threshold = 30.0  # Default fuel pressure minimum
            drop_warn = self.settings['fuel_drop_warn_percent']

        analysis.min_threshold = min_threshold

        if pressure_data is None:
            analysis.message = f'No {pressure_type} pressure channel found'
            return analysis

        pressure_in_pull = pressure_data[time_mask]
        if len(pressure_in_pull) == 0:
            return analysis

        # Overall stats
        analysis.average = float(np.mean(pressure_in_pull))
        analysis.minimum = float(np.min(pressure_in_pull))
        analysis.maximum = float(np.max(pressure_in_pull))

        # Calculate drop percentage from max
        if analysis.maximum > 0:
            analysis.drop_percent = ((analysis.maximum - analysis.minimum) / analysis.maximum) * 100

        # Determine status
        if analysis.minimum < min_threshold:
            analysis.status = 'fail'
            analysis.message = f'{pressure_type.title()} pressure dropped to {analysis.minimum:.0f} psi (min: {min_threshold})'
        elif analysis.drop_percent > drop_warn:
            analysis.status = 'warn'
            analysis.message = f'{pressure_type.title()} pressure dropped {analysis.drop_percent:.0f}%'
        else:
            analysis.status = 'pass'
            analysis.message = f'{pressure_type.title()} pressure stable ({analysis.minimum:.0f}-{analysis.maximum:.0f} psi)'

        # Per-RPM bin analysis
        if rpm_data is not None and len(rpm_bins) > 1:
            rpm_in_pull = rpm_data[time_mask]
            analysis.rpm_bins = [(rpm_bins[i] + rpm_bins[i+1]) / 2 for i in range(len(rpm_bins)-1)]

            for i in range(len(rpm_bins) - 1):
                bin_mask = (rpm_in_pull >= rpm_bins[i]) & (rpm_in_pull < rpm_bins[i+1])
                bin_pressure = pressure_in_pull[bin_mask]

                if len(bin_pressure) > 0:
                    bin_avg = float(np.mean(bin_pressure))
                    analysis.bin_averages.append(bin_avg)

                    if bin_avg < min_threshold:
                        analysis.bin_statuses.append('fail')
                    elif bin_avg < min_threshold * 1.2:
                        analysis.bin_statuses.append('warn')
                    else:
                        analysis.bin_statuses.append('pass')
                else:
                    analysis.bin_averages.append(None)
                    analysis.bin_statuses.append('none')

        return analysis

    def _analyze_timing(self,
                        time_mask: np.ndarray,
                        rpm_data: Optional[np.ndarray],
                        rpm_bins: List[int]) -> TimingAnalysis:
        """Analyze ignition timing."""
        analysis = TimingAnalysis()

        timing_data = self.get_channel_data('timing')

        if timing_data is None:
            analysis.message = 'No timing channel found'
            return analysis

        timing_in_pull = timing_data[time_mask]
        if len(timing_in_pull) == 0:
            return analysis

        # Overall stats
        analysis.average = float(np.mean(timing_in_pull))
        analysis.minimum = float(np.min(timing_in_pull))
        analysis.maximum = float(np.max(timing_in_pull))

        # Count significant retard events (timing drops > 3 degrees)
        if len(timing_in_pull) > 1:
            timing_diff = np.diff(timing_in_pull)
            analysis.retard_events = int(np.sum(timing_diff < -3))

        # Determine status
        if analysis.retard_events > 5:
            analysis.status = 'fail'
            analysis.message = f'{analysis.retard_events} timing retard events'
        elif analysis.retard_events > 0:
            analysis.status = 'warn'
            analysis.message = f'{analysis.retard_events} timing retard events'
        else:
            analysis.status = 'pass'
            analysis.message = f'Timing stable ({analysis.average:.1f}° avg)'

        # Per-RPM bin analysis
        if rpm_data is not None and len(rpm_bins) > 1:
            rpm_in_pull = rpm_data[time_mask]
            analysis.rpm_bins = [(rpm_bins[i] + rpm_bins[i+1]) / 2 for i in range(len(rpm_bins)-1)]

            for i in range(len(rpm_bins) - 1):
                bin_mask = (rpm_in_pull >= rpm_bins[i]) & (rpm_in_pull < rpm_bins[i+1])
                bin_timing = timing_in_pull[bin_mask]

                if len(bin_timing) > 0:
                    bin_avg = float(np.mean(bin_timing))
                    analysis.bin_averages.append(bin_avg)
                    analysis.bin_statuses.append('pass')  # Timing itself isn't good/bad
                else:
                    analysis.bin_averages.append(None)
                    analysis.bin_statuses.append('none')

        return analysis

    def _build_rpm_bin_table(self,
                             result: DynoPullResult,
                             rpm_bins: List[int]) -> List[RPMBinData]:
        """Build combined RPM bin table from individual analyses."""
        table = []

        if len(rpm_bins) < 2:
            return table

        num_bins = len(rpm_bins) - 1

        for i in range(num_bins):
            rpm_center = (rpm_bins[i] + rpm_bins[i+1]) / 2

            bin_data = RPMBinData(rpm=rpm_center)

            # AFR
            if i < len(result.afr.bin_averages):
                bin_data.afr = result.afr.bin_averages[i]

            # Knock
            if i < len(result.knock.bin_counts):
                bin_data.knock_count = result.knock.bin_counts[i]

            # Oil pressure
            if i < len(result.oil_pressure.bin_averages):
                bin_data.oil_psi = result.oil_pressure.bin_averages[i]

            # Fuel pressure
            if i < len(result.fuel_pressure.bin_averages):
                bin_data.fuel_psi = result.fuel_pressure.bin_averages[i]

            # Timing
            if i < len(result.timing.bin_averages):
                bin_data.timing_deg = result.timing.bin_averages[i]

            # Determine row status from worst individual status
            statuses = []
            if i < len(result.afr.bin_statuses):
                statuses.append(result.afr.bin_statuses[i])
            if i < len(result.knock.bin_statuses):
                statuses.append(result.knock.bin_statuses[i])
            if i < len(result.oil_pressure.bin_statuses):
                statuses.append(result.oil_pressure.bin_statuses[i])
            if i < len(result.fuel_pressure.bin_statuses):
                statuses.append(result.fuel_pressure.bin_statuses[i])

            if 'fail' in statuses:
                bin_data.status = 'fail'
            elif 'warn' in statuses:
                bin_data.status = 'warn'
            else:
                bin_data.status = 'pass'

            table.append(bin_data)

        return table
