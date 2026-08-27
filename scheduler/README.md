# Scheduling

The built-in foreground scheduler runs research independently from publishing. To run twice daily (every 12 hours / 720 minutes):

```powershell
news-agent daemon --topic "AI and developer tools" --every-minutes 720
```

## Autonomous Startup on PC Boot

The agent is configured to run automatically whenever your PC starts and you sign in:

1. **Scheduled Task**: Registered in Windows Task Scheduler as `Local Ollama News Agent` with an `AtLogOn` trigger.
2. **Startup Script**: [`scripts/start_news_agent.ps1`](../scripts/start_news_agent.ps1) boots Ollama if needed, starts the authenticated bridge, and launches the autonomous worker.
3. **Automation Worker**: [`scripts/automation_on_startup.ps1`](../scripts/automation_on_startup.ps1) runs exactly two startup-relative research/publish cycles: 15 minutes after login and four hours after the first cycle. A named mutex prevents duplicates.
4. **Destination Policy**: X and Threads are published publicly. The Short is uploaded through YouTube Studio with visibility forced to `PRIVATE`; public or unlisted requests are rejected.
5. **Registration / Setup**: To re-register or update the scheduled task at any time, run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\register_scheduled_task.ps1
```

Logs are appended to [`logs/autostart.log`](../logs/autostart.log), [`logs/automation_worker.log`](../logs/automation_worker.log), and [`logs/publisher.log`](../logs/publisher.log).
