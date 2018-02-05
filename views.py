from django.contrib.sites.shortcuts import get_current_site
from django.views.generic import FormView, TemplateView
from openinghours.models import OpeningHours

from admin_panels.forms import OpeningHoursForm, RestaurantLogoForm
from admin_panels.mixins import RestaurantMixin
from gloodny.models import Restaurant


class PanelGeneralInfoView(FormView):

    model = Restaurant
    context_object_name = "restaurant"
    template_name = 'admin/general-info.html'
    form_class = OpeningHoursForm
    success_url = 'general-info'

    def get_context_data(self, **kwargs):
        context = super(PanelGeneralInfoView, self).get_context_data(**kwargs)
        context[self.context_object_name] = self.get_object()
        context['logo_form'] = RestaurantLogoForm()
        return context

    def get_object(self, queryset=None):
        """
            get current restaurant
        """
        site = get_current_site(self.request)
        return Restaurant.get_by_site(site)

    def get_initial(self):
        """
        Returns the initial data to use for forms on this view.
        """
        return {'instance': self.get_object()}

    def form_valid(self, form):
        """
            Handle valid form
        """
        restaurant = self.get_object()
        restaurant.delete_openinghours()
        restaurant.create_openinghours(form.cleaned_data.iteritems())
        self.__update_logo(restaurant)
        return super(PanelGeneralInfoView, self).form_valid(form)

    def __update_logo(self, restaurant):
        if self.request.FILES:
            restaurant.logo = self.request.FILES.get('logo')
            restaurant.save()


class BaseAdminPanelView(RestaurantMixin, TemplateView):

    def get_context_data(self, **kwargs):
        context = super(BaseAdminPanelView, self).get_context_data(**kwargs)
        context['restaurant'] = self.restaurant
        return context
