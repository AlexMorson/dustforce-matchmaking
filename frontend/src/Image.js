import "./Image.css";

function Image({ level }) {
  return (
    <div className={"image"}>
      <a href={level.play}>
        <img alt={level.name} src={level.image} />
      </a>
      <span>{level.name}</span>
    </div>
  );
}

export default Image;
