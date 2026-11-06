from locust import HttpUser, task, between


class CommandParserUser(HttpUser):
    wait_time = between(1, 2)

    @task
    def parse_command(self):
        self.client.post(
            "/parse",
            json={"text": "Turn on the lights"}
        )