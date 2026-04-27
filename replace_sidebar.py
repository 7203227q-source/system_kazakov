import os
import re

def replace_sidebar(filepath, active_page):
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Regex to find <aside>...</aside> block
    pattern = re.compile(r'<aside[^>]*>.*?</aside>', re.DOTALL)
    
    # Replacement string
    replacement = f"{{% include 'core/includes/_tutor_sidebar.html' with active_page='{active_page}' %}}"
    
    new_content = pattern.sub(replacement, content, count=1)
    
    with open(filepath, 'w') as f:
        f.write(new_content)
    
    print(f"Updated {filepath}")

replace_sidebar('core/templates/core/tutor_dashboard.html', 'dashboard')
replace_sidebar('core/templates/core/tutor_task_bank.html', 'tasks')
replace_sidebar('core/templates/core/tutor_create_assignment.html', 'create_assignment')
replace_sidebar('core/templates/core/tutor_student_history.html', 'dashboard')
