"""A bounded photo-result window for a job's owner."""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.drf.request_user import request_user
from api.jobs.recent_photos import recent_job_photos
from api.models.long_running_job import LongRunningJob
from api.serializers.job import RecentJobPhotosSerializer


class JobRecentPhotosView(APIView):
    permission_classes = (IsAuthenticated,)
    pagination_class = None

    @extend_schema(responses=RecentJobPhotosSerializer)
    def get(self, request: Request, pk: int) -> Response:
        user = request_user(request)
        job = get_object_or_404(LongRunningJob.objects.owned_by(user), pk=pk)
        return Response(RecentJobPhotosSerializer(recent_job_photos(job, user)).data)
