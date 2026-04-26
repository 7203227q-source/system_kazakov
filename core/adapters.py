from allauth.account.adapter import DefaultAccountAdapter
from django.urls import reverse

class CustomAccountAdapter(DefaultAccountAdapter):
    def get_login_redirect_url(self, request):
        user = request.user
        
        # Если роль не выбрана (человек только что зашел через соцсеть)
        if user.role == 'unassigned':
            return reverse('select_role')
            
        # Обычный редирект по ролям
        if user.role == 'student':
            return reverse('student_dashboard')
        elif user.role == 'tutor':
            return reverse('tutor_dashboard')
        elif user.role == 'parent':
            return reverse('parent_dashboard')
        elif user.role == 'admin':
            return reverse('admin_dashboard')
            
        return super().get_login_redirect_url(request)
