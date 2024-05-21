from docx.shared import Pt

def set_paragraph_spacing(paragraph, space_before=0, space_after=0, line_spacing=1):
    """
    Set the spacing for a paragraph.

    Parameters:
    paragraph (docx.text.paragraph.Paragraph): The paragraph to format.
    space_before (float): Space before the paragraph in points.
    space_after (float): Space after the paragraph in points.
    line_spacing (float): Line spacing, where 1 is single, 2 is double, etc.
    """
    paragraph_format = paragraph.paragraph_format
    paragraph_format.space_before = Pt(space_before)
    paragraph_format.space_after = Pt(space_after)
    paragraph_format.line_spacing = line_spacing

def get_text_width(document):
    """
    Returns the text width in mm.
    """
    section = document.sections[0]
    return (section.page_width - section.left_margin - section.right_margin) / 36000