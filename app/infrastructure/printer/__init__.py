"""Printer adapters."""

from app.infrastructure.printer.pos58_printer import POS58Printer, PrinterError

__all__ = ["POS58Printer", "PrinterError"]
