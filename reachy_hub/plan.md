# Telemetry typed utterances

## User request and approval
Add one single-line input directly above the existing event filter, the same width, with a Send button.
Submit its contents to the running conversation app as a user utterance so instructions can be sent silently
or from another room. Use the existing telemetry logs for the robot's reaction.

The request was first recorded as deferred. Simon's "no field appeared" instructs implementation now.

## Approach
1. Verify that the installed conversation app's text-input RPC creates a user utterance, rather than speaking
   supplied text verbatim.
2. Add a small hub endpoint that forwards text to that RPC and returns a clear error on disconnection/rejection.
3. Add the input and Send button above the filter, with matching sizing. Enter also submits. Retain text on
   failure, prevent duplicate submissions while sending, and record submission/error in the existing event feed.
4. Test forwarding, invalid input, RPC errors/timeouts and the browser submit flow. Restart the current local
   hub after validation so refreshing the dashboard loads the working field and endpoint.

## Answer fields
- Placement and size? **Above the filter; single line; same width (answered by user).**
- What should Send do? **Submit a user utterance to the conversation app (answered by user).**
- Additional UI? **Only this field and Send button; reaction appears in telemetry logs (answered by user).**
- Implement now? **Yes: "no field appeared" following the feature request.**

## Delivered and verified 2026-10-15
- Implemented the requested field/button with shared grid columns for exact width alignment with the filter.
- Added `/api/utterances` and a bounded JSON-RPC client. Notifications are ignored while awaiting the matching
  acknowledgement; disconnection, rejection, invalid responses and timeouts are reported without automatic retries.
- Accepted instructions and delivery errors are recorded in the existing event feed. Failed sends retain text.
- 14 new tests pass, 43 focused tests pass, lint/type checks pass. Full unit suite: 124 passed, same 6 pre-existing
  experimental tracker failures.
- Restarted local telemetry at http://localhost:8710; previous snapshot saved before restart. The robot's
  conversation app was stopped when testing began and was started for the live test.
- Chrome checks confirm field placement/equal widths at desktop and phone emulation sizes, single pending send,
  text retention on error and clearing on success. Browser test's initial empty-required-field assertion was corrected
  by checking `validity.customError` rather than the native empty-field validation message.
- End-to-end: live input acknowledged; `utterance.sent` recorded; robot's final assistant transcript was
  "Text input works.". All four telemetry feeds connected. Temporary test browser closed.
