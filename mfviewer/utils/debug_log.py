"""
Debug logging system with benchmarking support for MFViewer.

Provides optional debug logging to file with timing/benchmark capabilities
for performance analysis.
"""

import logging
import time
import json
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from functools import wraps
from contextlib import contextmanager
from platformdirs import user_log_dir

# Global logger instance
_logger: Optional[logging.Logger] = None
_enabled: bool = False
_log_file_path: Optional[Path] = None
_benchmark_stats: Dict[str, Dict[str, Any]] = {}


def get_default_log_dir() -> Path:
    """Get the default log directory (platform-specific).

    Windows: %LOCALAPPDATA%/MFViewer/MFViewer/logs
    macOS: ~/Library/Logs/MFViewer
    Linux: ~/.local/state/mfviewer/log
    """
    log_dir = Path(user_log_dir("MFViewer", "MFViewer"))
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_default_log_file() -> Path:
    """Get the default log file path."""
    return get_default_log_dir() / "mfviewer_debug.log"


def get_settings_file() -> Path:
    """Get the path to the debug settings file."""
    from mfviewer.utils.config import TabConfiguration
    return TabConfiguration.get_default_config_dir() / "debug_settings.json"


def load_settings() -> Dict[str, Any]:
    """Load debug settings from file."""
    settings_file = get_settings_file()
    default_settings = {
        'enabled': False,
        'log_file': str(get_default_log_file()),
        'log_level': 'DEBUG',
        'include_benchmarks': True,
        'max_file_size_mb': 10,
        'backup_count': 3
    }

    if settings_file.exists():
        try:
            with open(settings_file, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                # Merge with defaults
                default_settings.update(saved)
        except Exception:
            pass

    return default_settings


def save_settings(settings: Dict[str, Any]) -> bool:
    """Save debug settings to file."""
    try:
        settings_file = get_settings_file()
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        with open(settings_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving debug settings: {e}")
        return False


def init_logging(
    enabled: bool = False,
    log_file: Optional[str] = None,
    log_level: str = 'DEBUG',
    max_file_size_mb: int = 10,
    backup_count: int = 3
) -> None:
    """
    Initialize the debug logging system.

    Args:
        enabled: Whether debug logging is enabled
        log_file: Path to the log file (uses default if None)
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        max_file_size_mb: Maximum log file size before rotation
        backup_count: Number of backup files to keep
    """
    global _logger, _enabled, _log_file_path

    _enabled = enabled

    if not enabled:
        _logger = None
        return

    # Set up log file path
    if log_file:
        _log_file_path = Path(log_file)
    else:
        _log_file_path = get_default_log_file()

    # Ensure directory exists
    _log_file_path.parent.mkdir(parents=True, exist_ok=True)

    # Create logger
    _logger = logging.getLogger('MFViewer')
    _logger.setLevel(getattr(logging, log_level.upper(), logging.DEBUG))

    # Remove existing handlers
    _logger.handlers.clear()

    # Create rotating file handler
    from logging.handlers import RotatingFileHandler
    handler = RotatingFileHandler(
        _log_file_path,
        maxBytes=max_file_size_mb * 1024 * 1024,
        backupCount=backup_count,
        encoding='utf-8'
    )

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s.%(msecs)03d | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    _logger.addHandler(handler)

    _logger.info("=" * 60)
    _logger.info("MFViewer Debug Logging Started")
    _logger.info(f"Log file: {_log_file_path}")
    _logger.info("=" * 60)


def init_from_settings() -> None:
    """Initialize logging from saved settings."""
    settings = load_settings()
    init_logging(
        enabled=settings.get('enabled', False),
        log_file=settings.get('log_file'),
        log_level=settings.get('log_level', 'DEBUG'),
        max_file_size_mb=settings.get('max_file_size_mb', 10),
        backup_count=settings.get('backup_count', 3)
    )


def is_enabled() -> bool:
    """Check if debug logging is enabled."""
    return _enabled and _logger is not None


def get_log_file_path() -> Optional[Path]:
    """Get the current log file path."""
    return _log_file_path


def debug(msg: str, *args, **kwargs) -> None:
    """Log a debug message."""
    if _logger and _enabled:
        _logger.debug(msg, *args, **kwargs)


def info(msg: str, *args, **kwargs) -> None:
    """Log an info message."""
    if _logger and _enabled:
        _logger.info(msg, *args, **kwargs)


def warning(msg: str, *args, **kwargs) -> None:
    """Log a warning message."""
    if _logger and _enabled:
        _logger.warning(msg, *args, **kwargs)


def error(msg: str, *args, **kwargs) -> None:
    """Log an error message."""
    if _logger and _enabled:
        _logger.error(msg, *args, **kwargs)


def exception(msg: str, *args, **kwargs) -> None:
    """Log an exception with traceback."""
    if _logger and _enabled:
        _logger.exception(msg, *args, **kwargs)


@contextmanager
def benchmark(operation_name: str, log_result: bool = True):
    """
    Context manager for benchmarking operations.

    Usage:
        with benchmark("Load CSV file"):
            # ... operation code ...

    Args:
        operation_name: Name of the operation being benchmarked
        log_result: Whether to log the result immediately

    Yields:
        A dict that can be used to store additional metrics
    """
    metrics = {'extra': {}}
    start_time = time.perf_counter()

    try:
        yield metrics
    finally:
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Update statistics
        if operation_name not in _benchmark_stats:
            _benchmark_stats[operation_name] = {
                'count': 0,
                'total_ms': 0.0,
                'min_ms': float('inf'),
                'max_ms': 0.0,
                'last_ms': 0.0
            }

        stats = _benchmark_stats[operation_name]
        stats['count'] += 1
        stats['total_ms'] += elapsed_ms
        stats['min_ms'] = min(stats['min_ms'], elapsed_ms)
        stats['max_ms'] = max(stats['max_ms'], elapsed_ms)
        stats['last_ms'] = elapsed_ms

        if log_result and _logger and _enabled:
            extra_info = ""
            if metrics['extra']:
                extra_parts = [f"{k}={v}" for k, v in metrics['extra'].items()]
                extra_info = f" | {', '.join(extra_parts)}"
            _logger.debug(f"BENCHMARK | {operation_name} | {elapsed_ms:.3f}ms{extra_info}")


def benchmark_func(operation_name: Optional[str] = None):
    """
    Decorator for benchmarking functions.

    Usage:
        @benchmark_func("Parse CSV")
        def parse_csv(file_path):
            ...

    Args:
        operation_name: Name of the operation (defaults to function name)
    """
    def decorator(func: Callable) -> Callable:
        name = operation_name or func.__name__

        @wraps(func)
        def wrapper(*args, **kwargs):
            with benchmark(name):
                return func(*args, **kwargs)

        return wrapper
    return decorator


def get_benchmark_stats() -> Dict[str, Dict[str, Any]]:
    """Get all benchmark statistics."""
    result = {}
    for op_name, stats in _benchmark_stats.items():
        result[op_name] = {
            'count': stats['count'],
            'total_ms': stats['total_ms'],
            'avg_ms': stats['total_ms'] / stats['count'] if stats['count'] > 0 else 0,
            'min_ms': stats['min_ms'] if stats['min_ms'] != float('inf') else 0,
            'max_ms': stats['max_ms'],
            'last_ms': stats['last_ms']
        }
    return result


def get_benchmark_summary() -> str:
    """Get a formatted summary of all benchmarks."""
    stats = get_benchmark_stats()
    if not stats:
        return "No benchmark data collected."

    lines = [
        "=" * 80,
        "BENCHMARK SUMMARY",
        "=" * 80,
        f"{'Operation':<40} {'Count':>8} {'Avg(ms)':>10} {'Min(ms)':>10} {'Max(ms)':>10}",
        "-" * 80
    ]

    for op_name in sorted(stats.keys()):
        s = stats[op_name]
        lines.append(
            f"{op_name:<40} {s['count']:>8} {s['avg_ms']:>10.3f} {s['min_ms']:>10.3f} {s['max_ms']:>10.3f}"
        )

    lines.append("=" * 80)
    return "\n".join(lines)


def log_benchmark_summary() -> None:
    """Log the benchmark summary."""
    if _logger and _enabled:
        _logger.info("\n" + get_benchmark_summary())


def clear_benchmark_stats() -> None:
    """Clear all benchmark statistics."""
    global _benchmark_stats
    _benchmark_stats = {}


def shutdown() -> None:
    """Shutdown the logging system cleanly."""
    global _logger, _enabled

    if _logger and _enabled:
        log_benchmark_summary()
        _logger.info("MFViewer Debug Logging Stopped")

        # Close all handlers
        for handler in _logger.handlers[:]:
            handler.close()
            _logger.removeHandler(handler)

    _logger = None
    _enabled = False
