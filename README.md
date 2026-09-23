# ContentHarvest

Веб-сервис для персональной агрегации полезного контента, собирающий все новые материалы из выбранных источников в структурированном виде.

## Структура репозитория

```
content_aggregator/
├── app/
│   ├── __init__.py
│   ├── main.py              
│   ├── config.py            
│   ├── database.py          
│   ├── deps.py               
│   ├── models.py             
│   ├── schemas.py            
│   ├── parser.py             
│   ├── scheduler.py          
│   ├── mailer.py             
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── sources.py        
│   │   └── items.py          
│   ├── templates/
│   │   ├── base.html
│   │   ├── sources.html      
│   │   ├── archive.html      
│   │   ├── stats.html        
│   │   └── email/digest.html 
│   └── static/
│       └── style.css
├── tests/
│   ├── __init__.py
│   ├── sample_feed.xml       
│   ├── sample_page.html      
│   ├── test_parser.py        
│   └── test_api.py           
├── scripts/
│   └── demo.py                
├── docs/
│   └── proposal.md            
├── .env.example
├── .gitignore
├── Procfile                  
├── requirements.txt
└── README.md
```

