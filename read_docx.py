import zipfile
import xml.etree.ElementTree as ET
import sys

def read_docx(path):
    with zipfile.ZipFile(path) as docx:
        tree = ET.fromstring(docx.read("word/document.xml"))
        namespaces = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        text = []
        for p in tree.iterfind('.//w:p', namespaces):
            texts = [t.text for t in p.iterfind('.//w:t', namespaces) if t.text]
            if texts:
                text.append(''.join(texts))
        return '\n'.join(text)

if __name__ == "__main__":
    print(f"--- Document: {sys.argv[1]} ---")
    print(read_docx(sys.argv[1]))
    print("\n" + "="*50 + "\n")
