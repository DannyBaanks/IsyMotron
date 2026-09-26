import { defineRailway, service } from "railway/iac";

export default defineRailway(() => {
  const ISyMotron = service("ISyMotron", {
    build: {
      builder: "DOCKERFILE",
      dockerfilePath: "Dockerfile.deploy",
    },
    deploy: {
      healthcheck: "/",
      healthcheckTimeout: 30,
    },
  });
  return { services: [ISyMotron] };
});
