from django.test import SimpleTestCase


class SdamgiaViewManyExtractTests(SimpleTestCase):
    def test_extracts_only_prob_nums_ids(self):
        from core.services_reshuege import extract_view_many_ids

        html = """
        <html><body>
          <span class="prob_nums">Тип 25 № <a href="/problem?id=111">111</a></span>
          <span class="prob_nums">Тип 25 № <a href="/problem?id=222">222</a></span>
          <a href="/problem?id=999">999</a>
          <a href="/problem?id=888">888</a>
        </body></html>
        """
        self.assertEqual(extract_view_many_ids(html, limit=None), ["111", "222"])

