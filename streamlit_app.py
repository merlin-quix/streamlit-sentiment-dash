import os
import streamlit as st
from dotenv import load_dotenv
import influxdb_client_3 as InfluxDBClient3
import pandas as pd
import time
import altair as alt
import datetime

os.environ["INFLUXDB_TOKEN"] = st.secrets.INFLUXDB_TOKEN
os.environ["INFLUXDB_HOST"] = st.secrets.INFLUXDB_HOST
os.environ["INFLUXDB_ORG"] = st.secrets.INFLUXDB_ORG
os.environ["INFLUXDB_DATABASE"] = st.secrets.INFLUXDB_DATABASE
os.environ["style_sheet"] = "style.css"
os.environ["chat_count"] ="3"
measurement_name = "conversations"

# Initialize the client variable
client = None

# Attempt to connect to InfluxDB
while client is None:
    try:
        print("Connecting client to InfluxDB...")
        time.sleep(1) 
        client = InfluxDBClient3.InfluxDBClient3(
            token="iWGU-RZ-AoML0bP4kjabHrqlB3IDtyLPAs_XMDpGOldEvQrzmtwC2Y-4arrkl1BX_bQpEvtYGgh16pJyviIsvA==",
            host="https://us-east-1-1.aws.cloud2.influxdata.com",
            org="ContentSquad",
            database="ConversationStore")
        # If the above line is successful, the code will break out of the loop
        print("Finished initializing client.")
    except Exception as e:
        print(f"Failed to connect to InfluxDB: {e}")
        print("Retrying in 1 second...")
        time.sleep(1)  # Wait for 1 second before retrying
    print("Client still None - Retrying again in 1 second...")
    time.sleep(1)  # Wait for 1 second before retrying

print("Setting page config...")

st.set_page_config(
    page_title="LLM Customer Support",
    page_icon="favicon.ico",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items=None
)

# apply custom css (optional)
with open(os.environ["style_sheet"]) as f:
    st.markdown('<style>{}</style>'.format(f.read()), unsafe_allow_html=True)

maxlen = int(os.environ["chat_count"])
containers = []
cols = st.columns([0.25, 0.25, 0.25, 0.25])

with cols[3]:
    chart_title = st.empty()
    chart = st.empty()

# two containers per conversation: one for the titles and stats, and the other for the messages
for i in range(maxlen):
    with cols[i % 3]:
        containers.append((st.empty(), st.empty()))

def get_chat_name(i: int):
    return f"Conversation #{i + 1}"

# customize Altair chart
alt_x = alt.X("time", axis=None)
alt_y = alt.Y("sentiment", axis=None)
alt_legend = alt.Legend(title=None, orient="bottom", direction="vertical")
alt_color = alt.Color("conversation", legend=alt_legend)

# emoji based on the sentiment
def get_emoji(sentiment: float):
    if sentiment > 0:
        return "😀"
    if sentiment < 0:
        return "😡"
    return "😐"

def get_customer_info(msg):
    # first message sent by the support agent does not have customer information
    if "customer_id" in msg:
        return f"{msg['customer_id']:.0f} ({msg['customer_name']}"
    return ""


# Initialize a list to store average sentiment values
average_sentiments = []
# Initialize a variable to store the start time for logging every second
sentiment_data = {}
sentiment_data["time"] = []
sentiment_data["average_sentiment"] = []

# main loop to poll InfluxDB for conversation updates and update the dashboard
while True:
    count = 0
    chats = []

    # Query InfluxDB 3.0 usinfg influxql or sql
    print("Running main query...")
    # Initialize the table variable
    table = None

    while table is None:
        try:
            table = client.query(query=
                f"""
                SELECT conversation_id, max(time) AS stime, COUNT(conversation_id) as ccount
                FROM conversations
                GROUP BY conversation_id
                ORDER BY stime DESC
                """)
        except Exception as e:
            print(f"Failed to complete query: {e}")
            print("Retrying in 1 second...")
            time.sleep(1)  # Wait for 1 second before retrying
    print("Finished running main query...")

    # Convert the result to a pandas dataframe. Required to be processed through Quix.
    df = table.to_pandas()

    df['stime'] = pd.to_datetime(df['stime'])
    df['ccount'] = df['ccount'].astype(int)

    # Filter for conversations with at least 5 messages
    conversations_with_min_messages = df[df['ccount'] >= 3]

    # Sort by 'stime' to get the most recent conversations
    top3 = conversations_with_min_messages.sort_values(by='stime', ascending=False).head(3)

    convo1id = top3.iloc[0]['conversation_id']
    convo2id = top3.iloc[1]['conversation_id']
    convo3id = top3.iloc[2]['conversation_id']

    # Query InfluxDB 3.0 to get the entire history of the FIRST most recently updated conversation 
    convostream1 = client.query(query=
                                f"""
    SELECT * FROM "conversations" 
    WHERE "conversation_id" = '{convo1id}'
    ORDER BY time ASC 
    """)
    ## Convert the result to a DataFrame
    cstream1 = convostream1.to_pandas()

    # Query InfluxDB 3.0 to get the entire history of the SECOND most recently updated conversation 
    convostream2 = client.query(query=
                                f"""
    SELECT * FROM "conversations" 
    WHERE "conversation_id" = '{convo2id}'
    ORDER BY time ASC 
    """)
    ## Convert the result to a DataFrame
    cstream2 = convostream2.to_pandas()

    # Query InfluxDB 3.0 to get the entire history of the THIRD most recently updated conversation
    convostream3 = client.query(query=
                                f"""
    SELECT * FROM "conversations" 
    WHERE "conversation_id" = '{convo3id}'
    ORDER BY time ASC 
    """)
    ## Convert the result to a DataFrame
    cstream3 = convostream3.to_pandas()

    # Clean glitches from the conversation history such as duplicate messages
    def clean_convo(convo_df):
        convo_df_filtered = convo_df.drop_duplicates(subset='text', keep='first').copy()
        # Create a new column 'prev_role' that is shifted by 1 row
        convo_df_filtered.loc[:, 'prev_role'] = convo_df_filtered['role'].shift(1)
        # Filter rows where 'role' is not equal to 'prev_role', this will remove consecutive duplicates
        convo_df_filtered = convo_df_filtered[convo_df_filtered['role'] != convo_df_filtered['prev_role']]
        # Drop the 'prev_role' column as it is no longer needed
        convo_df_filtered = convo_df_filtered.drop('prev_role', axis=1)
        convo_df_filtered = convo_df_filtered[convo_df_filtered['role'].isin(['agent', 'customer'])]
        return convo_df_filtered


    cstream1_filtered = clean_convo(cstream1)
    cstream2_filtered = clean_convo(cstream2)
    cstream3_filtered = clean_convo(cstream3)

    # Create a list of 3 converstations (dataframes) to iterate through 
    cs_dfs = [cstream1_filtered , cstream2_filtered, cstream3_filtered]

    for i in range(3):

        # clear old contents from containers
        c = containers[i]
        c[0].empty()
        c[1].empty()

        # get the average sentiment of the current conversation
        avgsent = cs_dfs[i]['sentiment'].mean()
        # append it to a dictionary for calulating the average across all 3 conversations
        average_sentiments.append(avgsent)

        # Get the most recent message (row) for extracting general conversational metadata
        msg_latest = cs_dfs[i].tail(1)
        # Convert the row from a dataframe to a normal dictionary
        msg_latest = msg_latest.iloc[0].to_dict()
        # Give a colored status to the average sentiment of the conversation
        mood_avg = ""
        if avgsent > 0:
            mood_avg = f"**:green[Good ({avgsent:.2f})]**"
        elif avgsent < 0:
            mood_avg = f"**:red[Bad ({avgsent:.2f})]**"
        else:
            mood_avg = f"**:orange[Neutral ({avgsent:.2f})]**"

        # Render the metadata from the latest message
        with c[0].container():
            st.subheader(f"Conversation #{i + 1}")
            st.markdown(f"**Agent ID:** {msg_latest['agent_id']:.0f} ({msg_latest['agent_name']})")
            st.markdown(f"**Customer ID:** {get_customer_info(msg_latest)})")
            st.markdown(f"**Average Sentiment:** {mood_avg}")
            st.markdown(f"**Product:** {msg_latest['customer_product']}")
            st.markdown(f"**Customer tone of voice:** {msg_latest['customer_mood']}")

            # Turn the current conversation dataframe into a dictionary for easier iteration
            cs_df = cs_dfs[i]
            cs_dict = cs_df.to_dict(orient='records')

            with c[1].container(border=True):
                for msg in cs_dict:
                    with st.chat_message("human" if msg["role"] == "customer" else "assistant"):
                        # a bit of custom html and css to align the sentiment nicely
                        st.markdown(
                            f"{msg['text']} <div style='text-align: right'>{get_emoji(msg['sentiment'])}</div>",
                            unsafe_allow_html=True)

    # Calculate the overall average sentiment from the collected 3 average sentiments
    if average_sentiments:
        overall_average_sentiment = sum(average_sentiments) / len(average_sentiments)
        # Append the overall average sentiment and the current time to the sentiment_data
        sentiment_data["time"].append(datetime.datetime.now())
        sentiment_data["average_sentiment"].append(overall_average_sentiment)
        # Clear the list after appending to sentiment_data
        # Reset the list after calculating the overall average
        average_sentiments = []
    else:
        overall_average_sentiment = 0

    # Log the overall average sentiment
    print(f"Overall average sentiment: {overall_average_sentiment}")

    # Ensure that only the last 60 entries are kept in the running "health check" for the overall sentiment
    max_entries = 60
    if len(sentiment_data["time"]) > max_entries:
        start_index = len(sentiment_data["time"]) - max_entries
        sentiment_data["time"] = sentiment_data["time"][start_index:]
        sentiment_data["average_sentiment"] = sentiment_data["average_sentiment"][start_index:]

    # sentiment dashboard
    if "time" in sentiment_data and len(sentiment_data["time"]) > 0:
        with chart_title.container():
            st.subheader("Customer Success Team")
            st.markdown("SENTIMENT DASHBOARD")
            st.markdown("#")
            st.markdown("Sentiment History")

        # Update the chart
        with chart.container():
            chart_data = pd.DataFrame(sentiment_data)
            y_min = -1
            y_max = 1
            chart_data.sort_values("time", inplace=True)
            alt_chart = alt.Chart(chart_data) \
                .mark_line(interpolate='step-after') \
                .encode(
                    x=alt.X("time:T", title="Time"),
                    y=alt.Y("average_sentiment:Q", title="Average Sentiment",scale=alt.Scale(domain=(y_min, y_max)))
                )
            st.altair_chart(alt_chart, use_container_width=True)

    time.sleep(1)

