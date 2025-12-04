# PAL MCP Name Change

PAL MCP was previously called Zen MCP. We renamed to avoid confusion with another similarly named product and to better reflect our role as a Provider Abstraction Layer for MCP. The software and workflows are the same; some configuration keys may still use `pal` during the transition, which we plan to migrate away from in subsequent updates.

Due to the change of name, you may need to run `run-server.sh` again to setup the new connection, and re-visit any `ZEN` name used within `.env` and change it to `PAL`. 