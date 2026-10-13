import matplotlib.pyplot as plt
import seaborn as sns
from collections import Counter
import re
from app.rag.chatbot import llm

def generate_summary(text: str) -> str:
    prompt = f"Please provide a detailed summary and analysis of the following text:\n\n{text[:4000]}"
    try:
        return llm.invoke(prompt)
    except Exception as e:
        return f"Summary generation failed: {e}"

def generate_plot(text: str, output_path: str):
    # Extract top keywords to create a simple analysis plot
    words = re.findall(r'\w+', text.lower())
    # Exclude common stop words roughly
    stopwords = {"the", "and", "is", "in", "it", "of", "to", "a", "for", "on", "with", "as", "by", "this", "that"}
    words = [w for w in words if len(w) > 3 and w not in stopwords]
    counts = Counter(words).most_common(10)
    
    if not counts:
        return
        
    labels, values = zip(*counts)
    
    plt.figure(figsize=(10, 6))
    sns.barplot(x=list(values), y=list(labels))
    plt.title("Top Keywords in Document")
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()
