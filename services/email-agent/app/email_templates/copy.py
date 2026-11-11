"""Short email copy shared with renderers and behavior tests."""

REPLY_PREFIX = "Re: "
CLARIFICATION_SUBJECT_LABEL = "Clarification needed"
REPLY_CHAIN_TIP = (
    "Tip: When replying, delete the quoted email conversation below to allow the server to "
    "focus on your clarification response. Keep the response brief and to the point."
)

GROUP_LABEL = "Group:"
CANNOT_CANCEL_EXPLANATION = (
    "This request has already been processed (or finished processing) and can no longer be\n"
    "cancelled. No action is required unless you would like to submit a new request."
)
UNRESOLVED_SPEAKERS_LEAD = (
    "The following speaker labels in the transcript could not be matched to a known group member,"
)
ASSESS_FINDINGS_HEADING = "Findings:"
ASSESS_GITHUB_HEADING = "From your group's GitHub"
NO_TRANSCRIPT_MATCH_TEXT = "I didn't find anything in past meeting transcripts that speaks to this."
GITHUB_UNAVAILABLE_NOTE = "Your group doesn't have a GitHub repo linked yet, so I couldn't check it."
TRELLO_UNAVAILABLE_NOTE = "Your group doesn't have a Trello board linked yet, so I couldn't check it."

HELP_SUBJECT = "What can I ask this system to do?"
CANCELLED_SUBJECT_PREFIX = "Cancelled — "
GROUP_MEMBER_SUBMIT_ACTION = "Submit a meeting transcript"
GROUP_MEMBER_ADD_COMMENT_ACTION = "Add a comment to a meeting"
GROUP_MEMBER_COMMENT_INSTRUCTION = (
    "Reply to that meeting's summary email, keep `group_id=<id>` and `meeting_id=<id>` in the "
    "subject, and write your comment in the reply body."
)

ADMIN_OVER_EMAIL_MARKER = "Administrator actions are not available over email"
ADMIN_OVER_EMAIL_EXPLANATION = (
    "Administrator actions, such as managing users or groups you don't belong to, can't be "
    "performed by email, even for administrators. Please use the web app or the API instead. "
    "Your normal access to your own groups still works by email."
)
