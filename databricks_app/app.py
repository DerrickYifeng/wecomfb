import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from typing import Optional
import os
import json

# Page configuration
st.set_page_config(
    page_title="用户反馈管理系统",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .feedback-card {
        background-color: white;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
        margin-bottom: 1rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)


class FeedbackDashboard:
    """Feedback Dashboard for Databricks App"""
    
    def __init__(self):
        # Storage backend configuration
        self.storage_backend = os.getenv("STORAGE_BACKEND", "uc")
        
        # Unity Catalog settings
        self.uc_catalog = os.getenv("UC_CATALOG", "dev")
        self.uc_schema = os.getenv("UC_SCHEMA", "inner_feedback")
        self.table_name = os.getenv("TABLE_NAME", "user_feedback")
        self.full_table_name = f"{self.uc_catalog}.{self.uc_schema}.{self.table_name}"
        
        # Databricks Connect settings
        self.databricks_host = os.getenv("DATABRICKS_HOST")
        self.databricks_token = os.getenv("DATABRICKS_TOKEN")
        
        # Local storage settings
        self.local_storage_path = os.getenv("LOCAL_STORAGE_PATH", "./data")
        
        # Initialize connection
        if self.storage_backend == "uc":
            self._init_databricks_connection()
        else:
            os.makedirs(self.local_storage_path, exist_ok=True)
    
    def _init_databricks_connection(self):
        """Initialize Databricks Connect"""
        try:
            from databricks.connect import DatabricksSession
            
            self.spark = DatabricksSession.builder \
                .remote(
                    host=self.databricks_host,
                    token=self.databricks_token
                ) \
                .getOrCreate()
            
            st.success(f"✅ Connected to Databricks: {self.databricks_host}")
        except Exception as e:
            st.error(f"❌ Failed to connect to Databricks: {e}")
            st.info("Falling back to local storage")
            self.storage_backend = "local"
            self.spark = None
    
    @st.cache_data(ttl=60)  # Cache for 60 seconds
    def load_feedback_data(_self, days: int = 30) -> pd.DataFrame:
        """Load feedback data from configured storage backend"""
        if _self.storage_backend == "uc":
            return _self._load_from_unity_catalog(days)
        else:
            return _self._load_from_local_storage(days)
    
    def _load_from_unity_catalog(_self, days: int) -> pd.DataFrame:
        """Load feedback data from Unity Catalog"""
        try:
            # Read from Unity Catalog
            df_spark = _self.spark.table(_self.full_table_name)
            
            # Filter by date
            from datetime import timedelta
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            df_spark = df_spark.filter(df_spark.created_at >= cutoff_date)
            
            # Order by created_at
            df_spark = df_spark.orderBy(df_spark.created_at.desc())
            
            # Convert to Pandas
            df = df_spark.toPandas()
            
            # Convert timestamp columns
            if 'created_at' in df.columns:
                df['created_at'] = pd.to_datetime(df['created_at'])
            if 'processed_at' in df.columns:
                df['processed_at'] = pd.to_datetime(df['processed_at'])
            
            return df
        except Exception as e:
            st.error(f"数据加载失败: {e}")
            return pd.DataFrame()
    
    def _load_from_local_storage(_self, days: int) -> pd.DataFrame:
        """Load feedback data from local JSON file"""
        try:
            feedback_file = os.path.join(_self.local_storage_path, "feedbacks.json")
            
            if not os.path.exists(feedback_file):
                return pd.DataFrame()
            
            with open(feedback_file, 'r', encoding='utf-8') as f:
                feedbacks = json.load(f)
            
            if not feedbacks:
                return pd.DataFrame()
            
            # Convert to DataFrame
            df = pd.DataFrame(feedbacks)
            
            # Convert timestamp columns
            if 'created_at' in df.columns:
                df['created_at'] = pd.to_datetime(df['created_at'])
            if 'processed_at' in df.columns:
                df['processed_at'] = pd.to_datetime(df['processed_at'])
            
            # Filter by date
            cutoff_date = datetime.now() - timedelta(days=days)
            df = df[df['created_at'] >= cutoff_date]
            
            # Sort by created_at
            df = df.sort_values('created_at', ascending=False)
            
            return df
        except Exception as e:
            st.error(f"数据加载失败: {e}")
            return pd.DataFrame()
    
    def update_feedback_status(self, feedback_id: str, is_processed: bool, notes: str = ""):
        """Update feedback processing status"""
        if self.storage_backend == "uc":
            self._update_in_unity_catalog(feedback_id, is_processed, notes)
        else:
            self._update_in_local_storage(feedback_id, is_processed, notes)
    
    def _update_in_unity_catalog(self, feedback_id: str, is_processed: bool, notes: str):
        """Update feedback in Unity Catalog"""
        try:
            from pyspark.sql.functions import current_timestamp, lit
            
            # Read table
            df = self.spark.table(self.full_table_name)
            
            # Update the specific row
            df_updated = df.withColumn(
                "is_processed",
                lit(is_processed).when(df.feedback_id == feedback_id, lit(is_processed)).otherwise(df.is_processed)
            ).withColumn(
                "processed_at",
                current_timestamp().when(df.feedback_id == feedback_id, current_timestamp()).otherwise(df.processed_at)
            ).withColumn(
                "notes",
                lit(notes).when(df.feedback_id == feedback_id, lit(notes)).otherwise(df.notes)
            )
            
            # Write back to table
            df_updated.write \
                .format("delta") \
                .mode("overwrite") \
                .option("overwriteSchema", "true") \
                .saveAsTable(self.full_table_name)
            
            st.success("状态更新成功！")
            st.cache_data.clear()  # Clear cache to refresh data
        except Exception as e:
            st.error(f"更新失败: {e}")
    
    def _update_in_local_storage(self, feedback_id: str, is_processed: bool, notes: str):
        """Update feedback in local storage"""
        try:
            feedback_file = os.path.join(self.local_storage_path, "feedbacks.json")
            
            with open(feedback_file, 'r', encoding='utf-8') as f:
                feedbacks = json.load(f)
            
            # Update the specific feedback
            for feedback in feedbacks:
                if feedback['feedback_id'] == feedback_id:
                    feedback['is_processed'] = is_processed
                    feedback['processed_at'] = datetime.now().isoformat()
                    feedback['notes'] = notes
                    break
            
            # Save back to file
            with open(feedback_file, 'w', encoding='utf-8') as f:
                json.dump(feedbacks, f, ensure_ascii=False, indent=2)
            
            st.success("状态更新成功！")
            st.cache_data.clear()  # Clear cache to refresh data
        except Exception as e:
            st.error(f"更新失败: {e}")


def render_metrics(df: pd.DataFrame):
    """Render key metrics"""
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="📊 总反馈数",
            value=len(df),
            delta=f"+{len(df[df['created_at'] > datetime.now() - timedelta(days=1)])} 今日"
        )
    
    with col2:
        bug_count = len(df[df['feedback_type'] == 'bug'])
        st.metric(
            label="🐛 Bug反馈",
            value=bug_count,
            delta=f"{bug_count/len(df)*100:.1f}%" if len(df) > 0 else "0%"
        )
    
    with col3:
        suggestion_count = len(df[df['feedback_type'] == 'suggestion'])
        st.metric(
            label="💡 建议反馈",
            value=suggestion_count,
            delta=f"{suggestion_count/len(df)*100:.1f}%" if len(df) > 0 else "0%"
        )
    
    with col4:
        processed_count = len(df[df['is_processed'] == True])
        st.metric(
            label="✅ 已处理",
            value=processed_count,
            delta=f"{processed_count/len(df)*100:.1f}%" if len(df) > 0 else "0%"
        )


def render_charts(df: pd.DataFrame):
    """Render visualization charts"""
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 反馈类型分布")
        if not df.empty:
            type_counts = df['feedback_type'].value_counts()
            fig = px.pie(
                values=type_counts.values,
                names=type_counts.index,
                title="反馈类型占比",
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("暂无数据")
    
    with col2:
        st.subheader("📅 每日反馈趋势")
        if not df.empty:
            daily_counts = df.groupby(df['created_at'].dt.date).size().reset_index()
            daily_counts.columns = ['日期', '反馈数']
            fig = px.line(
                daily_counts,
                x='日期',
                y='反馈数',
                title="每日反馈数量",
                markers=True
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("暂无数据")


def render_feedback_list(df: pd.DataFrame, dashboard: FeedbackDashboard):
    """Render feedback list with details"""
    st.subheader("📝 反馈详情列表")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        feedback_type_filter = st.multiselect(
            "反馈类型",
            options=df['feedback_type'].unique().tolist() if not df.empty else [],
            default=df['feedback_type'].unique().tolist() if not df.empty else []
        )
    
    with col2:
        status_filter = st.selectbox(
            "处理状态",
            options=["全部", "未处理", "已处理"],
            index=0
        )
    
    with col3:
        group_filter = st.multiselect(
            "群组",
            options=df['group_name'].unique().tolist() if not df.empty else [],
            default=df['group_name'].unique().tolist() if not df.empty else []
        )
    
    # Apply filters
    filtered_df = df.copy()
    if feedback_type_filter:
        filtered_df = filtered_df[filtered_df['feedback_type'].isin(feedback_type_filter)]
    if status_filter == "未处理":
        filtered_df = filtered_df[filtered_df['is_processed'] == False]
    elif status_filter == "已处理":
        filtered_df = filtered_df[filtered_df['is_processed'] == True]
    if group_filter:
        filtered_df = filtered_df[filtered_df['group_name'].isin(group_filter)]
    
    st.write(f"共 {len(filtered_df)} 条反馈")
    
    # Display feedback cards
    for idx, row in filtered_df.iterrows():
        with st.expander(
            f"{'✅' if row['is_processed'] else '⏳'} "
            f"{row['feedback_type'].upper()} - "
            f"{row['user_name']} - "
            f"{row['created_at'].strftime('%Y-%m-%d %H:%M')}"
        ):
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.markdown(f"**反馈内容：**")
                st.write(row['feedback_content'])
                st.markdown(f"**用户：** {row['user_name']} ({row['user_id']})")
                st.markdown(f"**群组：** {row['group_name']}")
                st.markdown(f"**时间：** {row['created_at']}")
                
                if row['notes']:
                    st.markdown(f"**备注：** {row['notes']}")
            
            with col2:
                st.markdown(f"**状态：** {'已处理 ✅' if row['is_processed'] else '未处理 ⏳'}")
                
                # Update status form
                with st.form(key=f"form_{row['feedback_id']}"):
                    new_status = st.checkbox(
                        "标记为已处理",
                        value=row['is_processed']
                    )
                    notes = st.text_area(
                        "备注",
                        value=row['notes'] if row['notes'] else "",
                        height=100
                    )
                    
                    if st.form_submit_button("更新"):
                        dashboard.update_feedback_status(
                            row['feedback_id'],
                            new_status,
                            notes
                        )
                        st.rerun()


def main():
    """Main application"""
    st.markdown('<h1 class="main-header">💬 用户反馈管理系统</h1>', unsafe_allow_html=True)
    
    # Initialize dashboard
    dashboard = FeedbackDashboard()
    
    # Sidebar
    with st.sidebar:
        st.header("⚙️ 设置")
        
        # Time range selector
        days = st.slider(
            "查看最近天数",
            min_value=1,
            max_value=90,
            value=30,
            step=1
        )
        
        # Refresh button
        if st.button("🔄 刷新数据", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        
        st.divider()
        
        # Info
        st.info("""
        **功能说明：**
        - 📊 查看反馈统计
        - 📈 分析反馈趋势
        - ✅ 管理反馈状态
        - 🔍 筛选和搜索
        """)
    
    # Load data
    with st.spinner("加载数据中..."):
        df = dashboard.load_feedback_data(days)
    
    if df.empty:
        st.warning("暂无反馈数据")
        st.info("请确保企业微信 Webhook 已正确配置并开始收集反馈数据")
        return
    
    # Render dashboard sections
    render_metrics(df)
    st.divider()
    render_charts(df)
    st.divider()
    render_feedback_list(df, dashboard)
    
    # Footer
    st.divider()
    st.markdown("""
    <div style='text-align: center; color: #666; padding: 2rem;'>
        <p>用户反馈管理系统 v2.0 | Powered by Databricks & Streamlit</p>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
