from finance_tracker import create_app

app = create_app()


if __name__ == "__main__":
    app.run(port=4848)
    
