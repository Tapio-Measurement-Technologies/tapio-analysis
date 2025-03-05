from abc import ABC, abstractmethod

class ReportGenerator(ABC):
    def __init__(self, report_data):
        self.report_data = report_data
        self.report_title = report_data.get('title', '')
        self.report_subtitle = report_data.get('subtitle', '')
        self.additional_info = report_data.get('additional_info', '')
        self.header_image_path = report_data.get('header_image_path', '')
        self.sample_image_path = report_data.get('sample_image_path', '')
        self.sections = report_data.get('sections', [])
        self.window_type = report_data.get('window_type', 'MD')

    @abstractmethod
    def generate(self, output_path):
        """Generate the report and save it to the specified path"""
        pass


def create_report_generator(report_type, report_data):
    """Factory function to create appropriate report generator"""
    generators = {
        'word': WordReportGenerator,
        'latex': LatexReportGenerator
    }

    generator_class = generators.get(report_type.lower())
    if not generator_class:
        raise ValueError(f"Unsupported report type: {report_type}")

    return generator_class(report_data)


# Import the concrete implementations after the base class and factory function
from .word_report_generator import WordReportGenerator
from .latex_report_generator import LatexReportGenerator
