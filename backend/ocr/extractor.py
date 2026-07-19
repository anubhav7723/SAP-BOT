import fitz
import os
import glob
import re

def clean_text(text):
    text = text.replace('\x00', '')
    text = re.sub(r'[ \t]+', ' ', text)
    
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        alnum_count = sum(c.isalnum() for c in line)
        if len(line) > 0 and (alnum_count / len(line)) < 0.1:
            continue
            
        cleaned_lines.append(line)
            
    return '\n'.join(cleaned_lines)

def main():
    directory = r"C:\Users\anubh\OneDrive\Documents\Projects\SAP-Chatbot\data"
    pdf_files = glob.glob(os.path.join(directory, "*.pdf"))
    
    if not pdf_files:
        print("No PDF files found in the directory.")
        return
        
    for pdf_path in pdf_files:
        print(f"Processing {os.path.basename(pdf_path)}...")
        try:
            doc = fitz.open(pdf_path)
            all_text = []
            for page_num, page in enumerate(doc):
                text = page.get_text("text")
                cleaned = clean_text(text)
                if cleaned:
                    all_text.append(f"--- Page {page_num + 1} ---\n{cleaned}")
            
            # Combine pages with double newline
            final_text = "\n\n".join(all_text)
            
            pdf_filename = os.path.basename(pdf_path)
            txt_filename = pdf_filename.rsplit('.', 1)[0] + ".txt"
            output_dir = os.path.join(directory, "text files")
            os.makedirs(output_dir, exist_ok=True)
            txt_path = os.path.join(output_dir, txt_filename)
            
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(final_text)
            
            print(f"Successfully converted and saved to {os.path.join('text files', txt_filename)}")
            doc.close()
        except Exception as e:
            print(f"Failed to convert {os.path.basename(pdf_path)}: {e}")

if __name__ == "__main__":
    main()