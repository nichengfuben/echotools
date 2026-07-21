"""fncall 解析器包。"""

from echotools.exec.fncall.parsers.stream import FncallStreamParser
from echotools.exec.fncall.parsers.xml_parser import parse_fncall, parse_fncall_xml

__all__ = ["parse_fncall", "parse_fncall_xml", "FncallStreamParser"]
